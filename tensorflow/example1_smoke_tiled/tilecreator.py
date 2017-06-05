#******************************************************************************
#
# MantaFlow fluid solver framework
# Copyright 2017 Daniel Hook
#
# This program is free software, distributed under the terms of the
# GNU General Public License (GPL) 
# http://www.gnu.org/licenses
#
# Create 2d tile data
#
#******************************************************************************

import uniio
import numpy as np
import scipy.misc
import os
import shutil
import copy
from shutil import copyfile
from random import randint

# global for tile creator
basePath = '../data/'

# arrays of tiles, excluding discarded ones
tile_inputs_all = []
tile_outputs_all = []

# arrays of all tiles, optional
tile_inputs_all_complete = []
tile_outputs_all_complete = []

combined_inputs_all = []
combined_outputs_all = []

combined_inputs_all_complete = []
combined_outputs_all_complete = []

tile_outputs_all_cropped = []
img_inputs_all = []
img_outputs_all = []

tile_data = {
	'inputs_train': [],
	'inputs_test': [],
	'inputs_val': [],

	'outputs_train': [],
	'outputs_test': [],
	'outputs_val': []
}

paths = {
	'base': '',
	'sim': '',
	'frame': '',
	'frame_low_uni': '',
	'frame_high_uni': '',
	'tiles': '',
	'tile_low_uni': '',
	'tile_high_uni': ''
}

def setBasePath(path):
	global basePath
	basePath = path

# note, creates uni and npz paths, even if only one of them is used at a time
def updatePaths(simNo=None, frameNo=None, tileNo=None, tile_size_x=0, tile_size_y=0, overlapping=0, data_type=None):
	paths['data_type'] = data_type
	paths['base'] = basePath
	paths['sim'] = paths['base'] + 'sim_%04d/' % simNo
	paths['frame'] = paths['sim'] + 'frame_%04d/' % frameNo 
	if overlapping > 0:
		paths['tiles'] = paths['frame'] + 'tiles_%02dx%02d_o%02d/' % (tile_size_x, tile_size_y, overlapping)
	else:
		paths['tiles'] = paths['frame'] + 'tiles_%02dx%02d/' % (tile_size_x, tile_size_y)

	paths['frame_low_uni']  = paths['frame'] + data_type + '_low_%04d_%04d.uni' % (simNo, frameNo)
	paths['frame_high_uni'] = paths['frame'] + data_type + '_high_%04d_%04d.uni' % (simNo, frameNo)
	paths['tile_low_uni']   = paths['tiles'] + data_type + '_low_%04d_%04d_%04d.uni' % (simNo, frameNo, tileNo)
	paths['tile_high_uni']  = paths['tiles'] + data_type + '_high_%04d_%04d_%04d.uni' % (simNo, frameNo, tileNo)

	# new numpy array filenames
	paths['frame_low_np']  = paths['frame_low_uni' ].replace('.uni', '.npz')
	paths['frame_high_np'] = paths['frame_high_uni'].replace('.uni', '.npz')
	paths['tile_low_np']   = paths['tile_low_uni'  ].replace('.uni', '.npz')  
	paths['tile_high_np']  = paths['tile_high_uni' ].replace('.uni', '.npz') 

	paths['tile_low_npb']  = paths['tiles'] + data_type + '_low_%04d_%04d' % (simNo, frameNo) #, tileNo)
	paths['tile_high_npb'] = paths['tiles'] + data_type + '_high_%04d_%04d' % (simNo, frameNo) #, tileNo)


#******************************************************************************
# I/O helper
# helper functions to load uni files into arrays with multiple channels

def uniToArray(uniPath, is_vel=False):
	head, content = uniio.readUni(uniPath)

	imageHeight = head['dimX']
	imageWidth  = head['dimY']
	#print(format(uniPath) + " " + format(head)) # debug info
	if not is_vel:
		fixedArray = np.zeros((imageHeight, imageWidth, 1), dtype='f')
	else:
		fixedArray = np.zeros((imageHeight, imageWidth, 3), dtype='f')

	if not is_vel:
		fixedArray = np.reshape(content, [imageWidth, imageHeight])
		fixedArray = fixedArray[::-1] # make a copy of the array in reverse order
	else:
		fixedArray = np.reshape(content, [imageWidth, imageHeight, 3])
		fixedArray = fixedArray[::-1]

	return fixedArray

def arrayToUni(input, savePath, motherUniPath, imageHeight, imageWidth, is_vel=False):
	head, _ = uniio.readUni(motherUniPath)
	head['dimX'] = imageWidth
	head['dimY'] = imageHeight

	if not is_vel:
		fixedArray = np.zeros((imageHeight, imageWidth), dtype='f')
		for x in range(0, imageHeight):
			for y in range(0, imageWidth):
				fixedArray[x][y] = input[(imageHeight - 1) - x][y]
	else:
		fixedArray = np.zeros((imageHeight, imageWidth, 3), dtype='f')
		for x in range(0, imageHeight):
			for y in range(0, imageWidth):
				fixedArray[x][y] = input[(imageHeight - 1) - x][y]

	uniio.writeUni(savePath, head, fixedArray)

def createPngFromUni(uniPath, save_path=''):
	if save_path == '':
		savePath = uniPath[:-3] + 'png'
	else:
		savePath = save_path

	array = uniToArray(uniPath)
	createPngFromArray(array, savePath)

# assumes single-channel 2d array
def createPngFromArray(input, savePath):
	imageHeight = len(input)
	imageWidth = len(input[0])

	fixedArray = np.zeros((imageHeight, imageWidth, 3), dtype='f')
	for x in range(0, imageHeight):
		for y in range(0, imageWidth):
			if (input[x][y] < 0.0):
				fixedArray[x][y][0] = -input[x][y]
			else:
				fixedArray[x][y][0] = input[x][y]
				fixedArray[x][y][1] = input[x][y]
				fixedArray[x][y][2] = input[x][y]



	scipy.misc.toimage(fixedArray, cmin=0.0, cmax=1.0).save(savePath)

# array can have multiple channels, use channel 0 for output
def createPngArrayChannel(input, savePath, channel=0):
	imageHeight = input.shape[0]
	imageWidth  = input.shape[1]

	fixedArray = np.zeros((imageHeight, imageWidth), dtype='f')
	for x in range(0, imageHeight):
		for y in range(0, imageWidth):
			v = input[x][y][channel]
			if (v < 0.0):
				fixedArray[x][y] = 0.0
			else:
				fixedArray[x][y] = v

	scipy.misc.toimage(fixedArray, cmin=0.0, cmax=1.0).save(savePath)


#******************************************************************************
# tiling

# break down single image into smaller tiles
def createTiles(input, imageHeight, imageWidth, tileHeight, tileWidth, overlapping=0):
	if ((imageHeight % tileHeight) != 0 |
		imageWidth % tileWidth != 0):
		print('Error: Image and tile size do not match.')

	tilesVertical = imageHeight // tileHeight
	tilesHorizontal = imageWidth // tileWidth

	tiles = []

	for currTileVert in range(0, tilesVertical):
		for currTileHor in range(0, tilesHorizontal):

			currTile = np.zeros((tileHeight + overlapping * 2, tileWidth + overlapping * 2), dtype='f')

			for currPixelVert in range(-overlapping, tileHeight + overlapping):
				for currPixelHor in range(-overlapping, tileWidth + overlapping):
					indexX = currPixelVert + (currTileVert * tileWidth)
					indexY = currPixelHor + (currTileHor * tileHeight)

					if (indexX >= 0) and (indexY >= 0) and (indexX < len(input)) and (indexY < len(input[0])):
						currTile[currPixelVert + overlapping][currPixelHor + overlapping] = input[indexX][indexY]
					else:
						currTile[currPixelVert + overlapping][currPixelHor + overlapping] = 0

			tiles.append(currTile)

	return tiles

def createTilesNumpy(data, tileShape, overlapping=0):
	dataShape = data.shape
	noTiles = [ dataShape[0]//tileShape[0], dataShape[1]//tileShape[1], dataShape[2]//tileShape[2] ]
	overlap = [overlapping,overlapping,overlapping]
	if dataShape[0]<=1:
		overlap[0] = 0
	channels = dataShape[3]
	tiles = []

	for tileZ in range(0, noTiles[0]):
		for tileY in range(0, noTiles[1]):
			for tileX in range(0, noTiles[2]): 
				tileIdx = [tileZ,tileY,tileX]
				currTile = np.zeros((tileShape[0] + overlap[0], tileShape[1] + overlap[1], tileShape[2] + overlap[2], channels), dtype='f')

				for z in range(-overlap[0]   , tileShape[0] + overlap[0]   ):
					for y in range(-overlap[1], tileShape[1] + overlap[1]):
						for x in range(-overlap[2], tileShape[2] + overlap[2]):
							zyx = [z,y,x]
							idx = [0,0,0]
							acc = [0,0,0]
							for i in range(3):
								idx[i] = zyx[i] + (tileIdx[i] * tileShape[i])
								if idx[i]<0: idx[i] = 0;
								if idx[i]>(dataShape[i]-1): idx[i] = (dataShape[i]-1);
								acc[i] = zyx[i] + overlap[i]
							currTile[acc[0],acc[1],acc[2]] = data[idx[0],idx[1],idx[2]] 

				tiles.append(currTile)

	return tiles

# concatenate an ordered list of tiles to form a single image
def combineTiles(tiles, imageHeight, imageWidth, tileHeight, tileWidth):
	if ((imageHeight % tileHeight) != 0 |
			imageWidth % tileWidth != 0):
		print('Error: Image and tile size do not match.')

	tilesVertical = imageHeight // tileHeight
	tilesHorizontal = imageWidth // tileWidth

	resultArray = np.zeros((imageHeight, imageWidth), dtype='f')

	for currTileVert in range(0, tilesVertical):
		for currTileHor in range(0, tilesHorizontal):

			for currPixelVert in range(0, tileHeight):
				for currPixelHor in range(0, tileWidth):
					indexX = currPixelHor + (currTileHor * tileHeight)
					indexY = currPixelVert + (currTileVert * tileWidth)

					resultArray[indexX][indexY] = (tiles[currTileHor * tilesHorizontal + currTileVert])[currPixelHor][currPixelVert]

	return resultArray

# combines velocity tiles (bad, close copy from combineTiles)
def combineTilesVelocity(tiles, imageHeight, imageWidth, tileHeight, tileWidth):
	if ((imageHeight % tileHeight) != 0 |
			imageWidth % tileWidth != 0):
		print('Error: Image and tile size do not match.')

	tilesVertical = imageHeight // tileHeight
	tilesHorizontal = imageWidth // tileWidth

	resultArray = np.zeros((imageHeight, imageWidth, 3), dtype='f')

	# for currTileVert in range(0, tilesVertical):
	# 	for currTileHor in range(0, tilesHorizontal):
    #
	# 		for currPixelVert in range(0, tileHeight):
	# 			for currPixelHor in range(0, tileWidth):
	# 				indexX = currPixelHor + (currTileHor * tileHeight)
	# 				indexY = currPixelVert + (currTileVert * tileWidth)
    #
	# 				resultArray[indexX][indexY] = (tiles[currTileHor * tilesHorizontal + currTileVert])[currPixelHor][currPixelVert]

	for currTileVert in range(0, tilesVertical):
		for currTileHor in range(0, tilesHorizontal):

			for currPixelVert in range(0, tileHeight):
				for currPixelHor in range(0, tileWidth):
					indexX = currPixelHor + (currTileHor * tileHeight)
					indexY = currPixelVert + (currTileVert * tileWidth)

					resultArray[indexX][indexY] = (tiles[currTileVert * tilesVertical + currTileHor])[currPixelHor][currPixelVert]

	return resultArray


#******************************************************************************
# higher level functions to organize test data

# save & load uni files
def createTestDataUni(simNo, tileSize, lowResSize, upScalingFactor, overlapping=0, createPngs=False, with_vel=False, with_pos=False):
	frameNo = 0
	tileNo = 0 
	data_type = 'density' 
	updatePaths(simNo, frameNo, tileNo, tileSize, tileSize, overlapping, data_type)

	# for each frame: create tiles + folders
	# print(paths['tiles'])
	while frameNo < 999:
		if os.path.exists(paths['frame']): 
			# print('Creating tiles for sim %04d, frame %04d' % (simNo, frameNo))
			if not os.path.exists(paths['tiles']):
				os.makedirs(paths['tiles'])

			# create tiles 
			if with_vel:
				lowArray = combineDensVelSpace(uniToArray(paths['frame_low_uni']), uniToArray(paths['frame_low_uni'].replace('density', 'vel'), is_vel=True))
				lowTiles = createTiles(lowArray, lowResSize * 2, lowResSize * 2, tileSize * 2, tileSize * 2, overlapping * 2)
			elif with_pos:
				lowArray = addPosToDensVelSpace(uniToArray(paths['frame_low_uni']), uniToArray(paths['frame_low_uni'].replace('density', 'vel'), is_vel=True))
				lowTiles = createTiles(lowArray, lowResSize * 3, lowResSize * 3, tileSize * 3, tileSize * 3, overlapping * 3)
			else:
				lowArray = uniToArray(paths['frame_low_uni'])
				lowTiles = createTiles(lowArray, lowResSize, lowResSize, tileSize, tileSize, overlapping)

			highArray = uniToArray(paths['frame_high_uni'])
			highTiles = createTiles(highArray, lowResSize * upScalingFactor, lowResSize * upScalingFactor, tileSize * upScalingFactor, tileSize * upScalingFactor, overlapping)

			for currTile in range(0, len(lowTiles)):
				if with_vel:
					arrayToUni(lowTiles[currTile], paths['tile_low_uni'].replace('density', 'dens_vel'), paths['frame_low_uni'], (tileSize + overlapping * 2) * 2, (tileSize + overlapping * 2) * 2)
				elif with_pos:
					arrayToUni(lowTiles[currTile], paths['tile_low_uni'].replace('density', 'dens_vel_pos'), paths['frame_low_uni'], (tileSize + overlapping * 2) * 3, (tileSize + overlapping * 2) * 3)
				else:
					arrayToUni(lowTiles[currTile], paths['tile_low_uni'], paths['frame_low_uni'], tileSize + overlapping * 2, tileSize + overlapping * 2)
				arrayToUni(highTiles[currTile], paths['tile_high_uni'], paths['frame_high_uni'], tileSize * upScalingFactor, tileSize * upScalingFactor)
				if createPngs:
					createPngFromUni(paths['tile_low_uni'].replace('density', 'dens_vel'))
					createPngFromUni(paths['tile_high_uni'])

				tileNo += 1
				updatePaths(simNo, frameNo, tileNo, tileSize, tileSize, overlapping, data_type)

		frameNo += 1
		tileNo = 0
		updatePaths(simNo, frameNo, tileNo, tileSize, tileSize, overlapping, data_type)

def loadTestDataUni(fromSim, toSim, densityMinimum, tileSizeLow, overlapping, partTrain=3, partTest=1, load_img=False, load_pos=False, load_vel=False, to_frame=200, low_res_size=64, upres=2):
	total_tiles_all_sim = 0
	discarded_tiles_all_sim = 0 
	data_type = 'density'

	for simNo in range(fromSim, toSim + 1):
		print('\nLoading sim %04d' % simNo)
		frameNo = 0
		tileNo = 0

		updatePaths(simNo, frameNo, tileNo, tileSizeLow, tileSizeLow, overlapping, data_type)
		print('from ' + paths['tiles'])
		# check if right tiles are available - create them if not
		if load_vel:
			pathCheck = paths['tile_low_uni'].replace('density', 'dens_vel')
		elif load_pos:
			pathCheck = paths['tile_low_uni'].replace('density', 'dens_vel_pos')
		else:
			pathCheck = paths['tile_low_uni']

		if not os.path.exists(paths['tiles']) or not os.path.exists(pathCheck):
			print('Could not find tiles for sim %04d. Creating new ones.' % simNo)
			createTestDataUni(simNo, tileSizeLow, low_res_size, upres, overlapping, with_vel=load_vel, with_pos=load_pos)
			updatePaths(simNo, frameNo, tileNo, tileSizeLow, tileSizeLow, overlapping, data_type)
		totalTiles = 0
		discardedTiles = 0

		while frameNo < to_frame:
			if load_img:
				lowArray = uniToArray(paths['frame_low_uni'])
				highArray = uniToArray(paths['frame_high_uni'])
				img_inputs_all.append(lowArray.flatten())
				img_outputs_all.append(highArray.flatten())

			#print('Loading frame %04d' % frameNo)
			while os.path.exists(paths['tile_high_uni']):
				# check if tile is empty. If so, don't add it
				accumulatedDensity = 0.0
				if load_vel:
					lowTile = uniToArray(paths['tile_low_uni'].replace('density', 'dens_vel'))
				elif load_pos:
					lowTile = uniToArray(paths['tile_low_uni'].replace('density', 'dens_vel_pos'))
				else:
					lowTile = uniToArray(paths['tile_low_uni'])
				highTile = uniToArray(paths['tile_high_uni'])

				for value in lowTile.flatten():
					accumulatedDensity += value
				if accumulatedDensity > (densityMinimum * tileSizeLow * tileSizeLow):
					tile_inputs_all.append(lowTile.flatten())
					tile_outputs_all.append(highTile.flatten())
				else:
					# print('Discarded empty tile.')
					discardedTiles += 1

				tile_inputs_all_complete.append(lowTile.flatten())
				tile_outputs_all_complete.append(highTile.flatten()) 
				totalTiles += 1

				tileNo += 1
				updatePaths(simNo, frameNo, tileNo, tileSizeLow, tileSizeLow, overlapping, data_type)

			tileNo = 0
			frameNo += 1
			updatePaths(simNo, frameNo, tileNo, tileSizeLow, tileSizeLow, overlapping, data_type)

		print('Total Tiles: %d' % totalTiles)
		print('Discarded Tiles: %d' % discardedTiles)
		print('Used Tiles: %d' % (totalTiles - discardedTiles))
		total_tiles_all_sim += totalTiles
		discarded_tiles_all_sim += discardedTiles

	print('Tiles in data set: %d' % (len(tile_inputs_all)) ) 
	if(len(tile_inputs_all)==0):
		print("No input tiles found!")
		exit(1)

	# split into train, test und val data

	parts_complete = partTrain + partTest 
	end_train = int( (len(tile_inputs_all) * partTrain / parts_complete) )  
	end_test = end_train + int( (len(tile_inputs_all) * partTest / parts_complete) )

	#print( "Debug out   %f   %f  %f  " % (len(tile_inputs_all), len(tile_inputs_all) // parts_complete, parts_complete ) )
	#print( "Ranges: len tile_inputs_all %d, end_train %d, end_test %d " % (len(tile_inputs_all), end_train, end_test) )
	tile_data['inputs_train'],  tile_data['inputs_test'],  tile_data['inputs_val']  = np.split(tile_inputs_all,  [end_train, end_test])
	tile_data['outputs_train'], tile_data['outputs_test'], tile_data['outputs_val'] = np.split(tile_outputs_all, [end_train, end_test])
	print('Training Sets: {}'.format(len(tile_data['inputs_train'])))
	print('Testing Sets:  {}'.format(len(tile_data['inputs_test'])))


#******************************************************************************
# higher level functions to organize test data , npz format

def assertShape3D(shape1, shape2, msg):
	#print("Comparing %s and %s " % (format(shape1),format(shape2)) )
	if not shape1[0] == shape2[0] or not shape1[1] == shape2[1] or not shape1[2] == shape2[2]:
		print('ERROR: Shape sizes for %s are incorrect. %s vs %s ' % (msg, format(shape1), format(shape2)) )
		exit()

# create npy data for a single frame; reads uni, writes numpy files
# note, supports 3d... not really tested so far
def createTestDataNpz(paths, tileSize, lowResSize, upScalingFactor, overlapping=0, createPngs=False, with_vel=False, with_pos=False, special_output_type='', dims=2, bWidth=-1):

	dataShape  = [lowResSize,lowResSize,lowResSize,1]
	if with_vel:
		dataShape[3] = 4
	elif with_pos:
		dataShape[3] = 7
	tileShape = [tileSize,tileSize,tileSize]
	if dims==2:
		tileShape[0] = 1
		dataShape[0] = 1
	dataType = paths['data_type']

	# for each frame: create tiles + folders, warning hard coded max 999
	#print('Creating tiles for sim %04d, frame %04d' % (simNo, frameNo))
	if not os.path.exists(paths['tiles']):
		os.makedirs(paths['tiles'])

	# create tiles 
	if with_vel:
		lowArray = combineChannelsFromUni(uniToArray(paths['frame_low_uni'].replace(dataType, 'density')), uniToArray(paths['frame_low_uni'].replace(dataType, 'vel'), is_vel=True))
	elif with_pos:                                                                                       
		lowArray = combineChannelsFromUni(uniToArray(paths['frame_low_uni'].replace(dataType, 'density')), uniToArray(paths['frame_low_uni'].replace(dataType, 'vel'), is_vel=True), addPos=True)
	else:
		lowArray = uniToArray(paths['frame_low_uni'].replace(dataType, 'density'))
		if len(lowArray.shape)==2: # add channels dimension if necessary
			lowArray = np.reshape(lowArray, [lowArray.shape[0], lowArray.shape[1], 1])

	# right now, all of the above return 2D (+channels) arrays, turn into 3D ...
	if dims==2:
		lowArray = np.reshape(lowArray, [1, lowArray.shape[0], lowArray.shape[1], lowArray.shape[2]])

	if bWidth >= 0:
		boundrySize = bWidth + 1
		dataShapeWithBoundry = [lowResSize + 2*boundrySize, lowResSize + 2*boundrySize, lowResSize + 2*boundrySize, dataShape[3]]
		if dims==2:
			dataShapeWithBoundry[0] = 1

		assertShape3D(lowArray.shape, dataShapeWithBoundry, "simulation with boundary")

		lowArray = np.reshape(lowArray, dataShapeWithBoundry)
		from_value = boundrySize
		to_value = lowResSize + boundrySize
		# avoid error "TypeError: slice indices must be integers or None or have an __index__ method"
		from_value = int(from_value)
		to_value = int(to_value)
		lowArray = lowArray[dataShapeWithBoundry[0] - 1, from_value: to_value, from_value: to_value]
		lowArray = np.reshape(lowArray, dataShape)
	else:
		assertShape3D(lowArray.shape, dataShape, "regular simulation")
		lowArray = np.reshape(lowArray, dataShape)
	lowTiles = createTilesNumpy(lowArray, tileShape, overlapping)

	#tilet2d = np.reshape( lowArray,(lowResSize,lowResSize,4) )
	#createPngArrayChannel( tilet2d , "/Users/sinithue/temp/tf/tout3a_%04d.png"%frameNo) # debug, write inputs again as images

	if special_output_type == '':
		highArray = uniToArray(paths['frame_high_uni'].replace(dataType, 'density'))
	else:
		# load input data with special name, e.g. "pressure"
		highArray = uniToArray(paths['frame_high_uni'].replace(dataType + '_high', special_output_type))
	if bWidth >= 0:
		boundrySize = bWidth + 1
		from_value = bWidth + 1
		to_value = (lowResSize * upScalingFactor) + boundrySize
		# avoid error "TypeError: slice indices must be integers or None or have an __index__ method"
		from_value = int(from_value)
		to_value = int(to_value)
		highArray = highArray[from_value: to_value, from_value: to_value]
	highTiles = createTiles(highArray, lowResSize * upScalingFactor, lowResSize * upScalingFactor, tileSize * upScalingFactor, tileSize * upScalingFactor, overlapping)

	if 0: # debug info
		print('Sim dimensions low %s, high %s' % (format(lowArray.shape), format(highArray.shape)) )

	for currTile in range(0, len(lowTiles)):
		if with_vel:
			uniio.writeNumpyBuf( paths['tile_low_npb'].replace(dataType, 'dens_vel'),     lowTiles[currTile] )
		elif with_pos:
			uniio.writeNumpyBuf( paths['tile_low_npb'].replace(dataType, 'dens_vel_pos'), lowTiles[currTile] )
		else:
			uniio.writeNumpyBuf( paths['tile_low_npb']                                  , lowTiles[currTile] )

		if special_output_type == '':
			uniio.writeNumpyBuf( paths['tile_high_npb'], highTiles[currTile] )
		else:
			# load input data with special name, e.g. "pressure"
			uniio.writeNumpyBuf( paths['tile_high_npb'].replace(dataType + '_high', special_output_type), highTiles[currTile] )

	uniio.finalizeNumpyBufs()

def loadTestDataNpz(fromSim, toSim, densityMinimum, tileSizeLow, overlapping, partTrain=3, partTest=1, load_pos=False, load_vel=False, special_output_type='', to_frame=200, low_res_size=64, upres=2, keepAll=False, bWidth=-1):
	total_tiles_all_sim = 0
	discarded_tiles_all_sim = 0 
	dataType = 'density'
	if load_vel:
		dataType = 'dens_vel'
	elif load_pos:
		dataType = 'dens_vel_pos'

	for simNo in range(fromSim, toSim + 1):
		frameNo  = 0
		bufferNo = 0  # note, replaces tile-number here

		updatePaths(simNo, frameNo, bufferNo, tileSizeLow, tileSizeLow, overlapping, dataType)
		print('\nLoading sim %04d from %s' % (simNo, paths['tiles']) )
		totalTiles = 0
		discardedTiles = 0

		while frameNo < to_frame:
			# recreate per frame
			if os.path.exists(paths['frame']) and ( not os.path.exists(paths['tiles']) or not os.path.exists( paths['tile_low_np'] ) ):
				print('Could not find tiles for sim %04d, frame %d. Creating new ones.' % (simNo,frameNo) )
				createTestDataNpz(paths, tileSizeLow, low_res_size, upres, overlapping, with_vel=load_vel, with_pos=load_pos, special_output_type=special_output_type, bWidth=bWidth)

			#print('Loading np buffers for frame %04d' % frameNo)
			#print(paths['tile_high_np'])
			while os.path.exists(paths['tile_low_np']):
				# check if tile is empty. If so, don't add it
				ltPath = paths['tile_low_np']

				lowTiles  = uniio.readNumpy(ltPath)
				if special_output_type == '':
					highTiles = uniio.readNumpy(paths['tile_high_np'])
				else:
					highTiles = uniio.readNumpy(paths['tile_high_np'].replace(dataType + '_high', special_output_type))
				if len(lowTiles.files) != len(highTiles.files):
					print("Error - tile file entries don't match! %d vs %d" % (len(lowTiles) , len(highTiles)) )

				for i in range(len( lowTiles.files )):
					lowTile  = lowTiles[ "arr_%d"%i ]
					highTile = highTiles[ "arr_%d"%i ]

					totalDens = lowTile.sum( dtype=np.float64 )
					#print("sum %f %f " % (accumulatedDensity,totalDens) )
					if totalDens > (densityMinimum * tileSizeLow * tileSizeLow):
						tile_inputs_all.append(lowTile.flatten())
						tile_outputs_all.append(highTile.flatten())
					else:
						# print('Discarded empty tile.')
						discardedTiles += 1

					if keepAll:
						tile_inputs_all_complete.append(lowTile.flatten()) 
						tile_outputs_all_complete.append(highTile.flatten())
					totalTiles += 1

				bufferNo   += 1
				updatePaths(simNo, frameNo, bufferNo, tileSizeLow, tileSizeLow, overlapping, dataType)

			bufferNo = 0
			frameNo += 1
			updatePaths(simNo, frameNo, bufferNo, tileSizeLow, tileSizeLow, overlapping, dataType)

		if 0 and len(lowTiles.files)>0:
			print('Tile dimensions low %s high %s' % (format(lowTiles["arr_%d"%0].shape), format(highTiles["arr_%d"%0].shape)) )
		print('Total Tiles: %d' % totalTiles)
		print('Discarded Tiles: %d' % discardedTiles)
		print('Used Tiles: %d' % (totalTiles - discardedTiles))
		total_tiles_all_sim += totalTiles
		discarded_tiles_all_sim += discardedTiles

	if 0: # NT_DEBUG , output all inputs as images
		i =0
		for tile in tile_inputs_all:
			tile2d = np.reshape( tile,(tileSizeLow,tileSizeLow,4) )
			print (format(tile2d.shape))
			createPngArrayChannel( tile2d , "/Users/sinithue/temp/tf/tout3b_%04d.png"%i) # NT_DEBUG
			i+=1
		exit(1) # NT_DEBUG


	print('Tiles in data set: %d' % (len(tile_inputs_all)) ) 
	if(len(tile_inputs_all)==0):
		print("No input tiles found!")
		exit(1)

	# split into train, test und val data 
	parts_complete = partTrain + partTest 
	end_train = int( (len(tile_inputs_all) * partTrain / parts_complete) )  
	end_test = end_train + int( (len(tile_inputs_all) * partTest / parts_complete) )

	#print( "Debug out   %f   %f  %f  " % (len(tile_inputs_all), len(tile_inputs_all) // parts_complete, parts_complete ) )
	#print( "Ranges: len tile_inputs_all %d, end_train %d, end_test %d " % (len(tile_inputs_all), end_train, end_test) )
	tile_data['inputs_train'],  tile_data['inputs_test'],  tile_data['inputs_val']  = np.split(tile_inputs_all,  [end_train, end_test])
	tile_data['outputs_train'], tile_data['outputs_test'], tile_data['outputs_val'] = np.split(tile_outputs_all, [end_train, end_test])
	print('Training set: {}'.format(len(tile_data['inputs_train'])))
	print('Testing set:  {}'.format(len(tile_data['inputs_test'])))


#******************************************************************************
# misc smaller helpers for output

def selectRandomTiles(selectionSize, isTraining=True, cropped=False):
	# returns #selectionsize elements of inputs_train/test and outputs_train/test
	allInputs = tile_data['inputs_train']
	if not cropped:
		allOutputs = tile_data['outputs_train']
	else:
		allOutputs = tile_outputs_all_cropped

	if not isTraining:
		allInputs = tile_data['inputs_test']
		allOutputs = tile_data['outputs_test']

	selectedInputs = []
	selectedOutputs = []
	inputSize = len(allInputs) - 1
	for currNo in range(0, selectionSize):
		randNo = randint(0, inputSize)
		selectedInputs.append(allInputs[randNo])
		selectedOutputs.append(allOutputs[randNo])

	return selectedInputs, selectedOutputs

# combine data into multiple channels of higher dimensional array
def combineChannelsFromUni(low_tile_density, low_tile_vel, addPos=False):
	shape = low_tile_density.shape

	if 0:
		print( "debug combineDensVelChannels") # NT_DEBUG
		print( format(shape) )
		#print( format(len(low_tile_density)) )
		print( format(low_tile_density.flags) )
		print( format(low_tile_density.strides ) )
		exit(1)

	# Combines one tile of density with one tile of velocity
	channels = 4
	if addPos:
		channels += 3 
	output_tile = np.zeros((shape[1], shape[0], channels), dtype='f')

	for curr_pos_y in range(shape[0]):
		for curr_pos_x in range(shape[1]):
			output_tile[curr_pos_y][curr_pos_x][0] = low_tile_density[curr_pos_y][curr_pos_x]
			output_tile[curr_pos_y][curr_pos_x][1] = low_tile_vel[curr_pos_y][curr_pos_x][0]
			output_tile[curr_pos_y][curr_pos_x][2] = low_tile_vel[curr_pos_y][curr_pos_x][1]
			output_tile[curr_pos_y][curr_pos_x][3] = low_tile_vel[curr_pos_y][curr_pos_x][2]
			if addPos:
				output_tile[curr_pos_y][curr_pos_x][4] = curr_pos_x / float(shape[1])
				output_tile[curr_pos_y][curr_pos_x][5] = curr_pos_y / float(shape[0])
				output_tile[curr_pos_y][curr_pos_x][6] = 0.

	#createPngFromArray(output_tile, basePath + 'debugOut.png')
	return output_tile

# arrange data spatially into larger single channel array
def combineDensVelSpace(low_tile_density, low_tile_vel):
	# Combines one tile of density with one tile of velocity
	output_tile = np.zeros((len(low_tile_density) * 2, len(low_tile_density) * 2), dtype='f')

	for curr_pos_x in range(len(low_tile_density)):
		for curr_pos_y in range(len(low_tile_density)):
			output_tile[curr_pos_x * 2	][curr_pos_y * 2	] = low_tile_density[curr_pos_x][curr_pos_y]
			output_tile[curr_pos_x * 2 + 1][curr_pos_y * 2	] = low_tile_vel[curr_pos_x][curr_pos_y][0]
			output_tile[curr_pos_x * 2	][curr_pos_y * 2 + 1] = low_tile_vel[curr_pos_x][curr_pos_y][1]
			output_tile[curr_pos_x * 2 + 1][curr_pos_y * 2 + 1] = low_tile_vel[curr_pos_x][curr_pos_y][2]

	#createPngFromArray(output_tile, basePath + 'debugOut.png')
	return output_tile

def addPosToDensVelSpace(low_tile_density, low_tile_vel):
	output_tile = np.zeros((len(low_tile_density) * 3, len(low_tile_density) * 3), dtype='f')
	pos = []

	for x in range(len(low_tile_density)):
		pos.append(np.linspace(0., 1., len(low_tile_density)))

	for curr_pos_x in range(len(low_tile_density)):
		for curr_pos_y in range(len(low_tile_density)):
			output_tile[curr_pos_x * 3	][curr_pos_y * 3	] = low_tile_density[curr_pos_x][curr_pos_y]
			output_tile[curr_pos_x * 3 + 1][curr_pos_y * 3	] = low_tile_vel[curr_pos_x][curr_pos_y][0]
			output_tile[curr_pos_x * 3	][curr_pos_y * 3 + 1] = low_tile_vel[curr_pos_x][curr_pos_y][1]
			output_tile[curr_pos_x * 3 + 1][curr_pos_y * 3 + 1] = low_tile_vel[curr_pos_x][curr_pos_y][2]
			output_tile[curr_pos_x * 3	][curr_pos_y * 3 + 2] = pos[curr_pos_x][curr_pos_y]
			output_tile[curr_pos_x * 3 + 1][curr_pos_y * 3 + 2] = pos[curr_pos_y][curr_pos_x]

	#createPngFromArray(output_tile, basePath + 'debugOutP.png')
	return output_tile

def splitTileData(partTrain=3, partTest=1):
	parts_complete = partTrain + partTest
	end_train = int((len(tile_inputs_all) * partTrain / parts_complete))
	end_test = end_train + int((len(tile_inputs_all) * partTest / parts_complete))

	tile_data['inputs_train'], tile_data['inputs_test'], tile_data['inputs_val'] = np.split(tile_inputs_all, [end_train, end_test])
	tile_data['outputs_train'], tile_data['outputs_test'], tile_data['outputs_val'] = np.split(tile_outputs_all, [end_train, end_test])

def reduceTo2DVelocity(tile, tileSizeLow):
	# dont use this, use reduceInputsTo2DVelocity
	# reduces one tile with density and velocity to the x and y of the velocity
	curr_tile = np.reshape(tile, (4, tileSizeLow * tileSizeLow), order='F')
	tile = [curr_tile[1], curr_tile[2]]
	return np.array(tile).flatten()

def reduceInputsTo2DVelocity():
	# reduces tile inputs with density and velocity to the x and y of the velocity
	calc_tile = np.array(tile_inputs_all[0])
	tileSizeLow = int(scipy.sqrt(calc_tile.shape[0] / 4))

	new_tile_inputs_all_complete = []
	for curr_tile in tile_inputs_all_complete:
		new_tile_inputs_all_complete.append(reduceTo2DVelocity(curr_tile, tileSizeLow))
	del tile_inputs_all_complete[:]
	for curr_tile in new_tile_inputs_all_complete:
		tile_inputs_all_complete.append(curr_tile)

	new_tile_inputs_all = []
	for curr_tile in tile_inputs_all:
		new_tile_inputs_all.append(reduceTo2DVelocity(curr_tile, tileSizeLow))
	del tile_inputs_all[:]
	for curr_tile in new_tile_inputs_all:
		tile_inputs_all.append(curr_tile)

def shuffleInputs(a, b):
	rng_state = np.random.get_state()
	np.random.shuffle(a)
	np.random.set_state(rng_state)
	np.random.shuffle(b)
	return a, b

def debugOutputPngs(input, expected, output, tileSizeLow, tileSizeHigh, imageSizeLow, imageSizeHigh, path, imageCounter=0):
	expectedArray = []
	outputArray = []
	inputArray = []

	tileCounter = 0
	for currTile in range(0, len(input)):
		expectedArray.append(np.reshape(expected[currTile], (tileSizeHigh, tileSizeHigh)))
		outputArray.append(np.reshape(output[currTile], (tileSizeHigh, tileSizeHigh)))
		# inputArray.append(np.reshape(input[currTile], (tileSizeLow, tileSizeLow)))

		tileCounter += 1

		if tileCounter == ((imageSizeLow // tileSizeLow) ** 2):
			imageCounter += 1
			tileCounter = 0

			expectedImage = combineTiles(expectedArray, imageSizeHigh, imageSizeHigh, tileSizeHigh, tileSizeHigh)
			outputImage   = combineTiles(outputArray, imageSizeHigh, imageSizeHigh, tileSizeHigh, tileSizeHigh)
			# inputImage = combineTiles(inputArray, imageSizeLow, imageSizeLow, tileSizeLow, tileSizeLow)

			createPngFromArray(expectedImage, path + 'ref_%04d.png' % imageCounter)
			createPngFromArray(outputImage, path + 'debout_%04d.png' % imageCounter)
			# createPngFromArray(inputImage, path + 'full_%04d_1.png' % imageCounter)

			expectedArray = []
			outputArray = []
			inputArray = []

def debugOutputPngsSingle(input, tileSize, imageSize, path, imageCounter=0, name='input'):
	# creates output png from tiles (that form an image)
	inputArray = []

	tileCounter = 0
	for currTile in range(0, len(input)):
		inputArray.append(np.reshape(input[currTile], (tileSize, tileSize)))

		tileCounter += 1

		if tileCounter == ((imageSize // tileSize) ** 2):
			imageCounter += 1
			tileCounter = 0

			inputImage = combineTiles(inputArray, imageSize, imageSize, tileSize, tileSize)
			createPngFromArray(inputImage, path + name + '_%04d.png' % imageCounter)

			inputArray = []

# Edited for cropping: Added this method. Nearly the same as the original one, didn't want to ruin the original one.
def debugOutputPngsCrop(tiles, tileSizeHigh, imageSizeHigh, path, imageCounter=0, cut_output_to=-1, tiles_in_image=-1, name=''):
	expectedArray = []
	outputArray = []
	tileCounter = 0

	for currTile in range(0, len(tiles)):
		if cut_output_to == -1:
			outputArray.append(np.reshape(tiles[currTile], (tileSizeHigh, tileSizeHigh)))
		else:
			from_value = (tileSizeHigh - cut_output_to) / 2
			to_value = tileSizeHigh - from_value
			# avoid error "TypeError: slice indices must be integers or None or have an __index__ method"
			from_value = int(from_value)
			to_value   = int(to_value)
			output_tile = np.reshape(tiles[currTile], (tileSizeHigh, tileSizeHigh))
			outputArray.append(output_tile[from_value: to_value, from_value: to_value])

		tileCounter += 1 
		if tileCounter == (tiles_in_image):
			imageCounter += 1
			tileCounter = 0

			if cut_output_to == -1:
				outputImage = combineTiles(outputArray, imageSizeHigh, imageSizeHigh, tileSizeHigh, tileSizeHigh)
			else:
				outputImage = combineTiles(outputArray, imageSizeHigh, imageSizeHigh, cut_output_to, cut_output_to)

			if not name == '':
				createPngFromArray(outputImage, path + name + '_%04d.png' % imageCounter)
			else:
				createPngFromArray(outputImage, path + 'full_%04d.png' % imageCounter)
			outputArray = []

def create_png_for_sims(from_sim, to_sim, target_folder):
	# target_folder with / at the end
	frame_global_no = 0

	for simNo in range(from_sim, to_sim + 1):
		frameNo = 0

		updatePaths(simNo, frameNo, 0, 0, 0, 0, 'density')

		while os.path.exists(paths['frame']):
			createPngFromUni(paths['frame_low_uni'], target_folder + 'frame_%04d_2.png' % frame_global_no)
			createPngFromUni(paths['frame_high_uni'], target_folder + 'frame_%04d_3.png' % frame_global_no)

			frameNo += 1
			frame_global_no += 1
			updatePaths(simNo, frameNo, 0, 0, 0, 0, 'density')

# deep copy of sim data tree (only dens & vel, no tiles, only uni files)
def copySimData(fromSim, toSim, to_frame=200):
	total_tiles_all_sim = 0
	discarded_tiles_all_sim = 0 
	dt_dens = 'density'
	dt_vel  = 'vel'

	#for simNo in range(fromSim, toSim + 1):
	simNo = fromSim
	if 1:
		print('\nCopying sim %04d' % simNo)
		frameNo = 0
		tileNo = 0

		updatePaths(simNo, frameNo, tileNo, 0, 0, 0, dt_dens )
		pathsFrom = copy.deepcopy(paths)
		updatePaths(toSim, frameNo, tileNo, 0, 0, 0, dt_dens )
		pathsTo = copy.deepcopy(paths)
		print('To ' + pathsTo['sim'])

		if not os.path.isdir( pathsTo['sim'] ):
			os.makedirs(pathsTo['sim'])

		while frameNo < to_frame:
			updatePaths(simNo, frameNo, tileNo, 0, 0, 0, dt_dens )
			pathsFrom = copy.deepcopy(paths)
			updatePaths(toSim, frameNo, tileNo, 0, 0, 0, dt_dens )
			pathsTo = copy.deepcopy(paths)

			if not os.path.isdir( pathsFrom['frame'] ):
				frameNo += 1
				continue;

			if not os.path.isdir( pathsTo['frame'] ):
				os.makedirs(pathsTo['frame'])

			if os.path.isfile( pathsFrom['frame_low_uni'] ):
				print('   copy ' + pathsFrom['frame_low_uni']+ " " + pathsTo['frame_low_uni'] )
				shutil.copyfile( pathsFrom['frame_low_uni'],  pathsTo['frame_low_uni'] )
			if os.path.isfile( pathsFrom['frame_high_uni'] ):
				print('   copy ' + pathsFrom['frame_high_uni']+ " " + pathsTo['frame_high_uni'] )
				shutil.copyfile( pathsFrom['frame_high_uni'], pathsTo['frame_high_uni'] )

			updatePaths(simNo, frameNo, tileNo, 0, 0, 0, dt_vel )
			pathsFrom = copy.deepcopy(paths)
			updatePaths(toSim, frameNo, tileNo, 0, 0, 0, dt_vel )
			pathsTo = copy.deepcopy(paths)

			if os.path.isfile( pathsFrom['frame_low_uni'] ):
				print('   copy vel ' + pathsFrom['frame_low_uni']+ " " + pathsTo['frame_low_uni'] )
				shutil.copyfile( pathsFrom['frame_low_uni'] , pathsTo['frame_low_uni'] )
			if os.path.isfile( pathsFrom['frame_high_uni'] ):
				print('   copy vel ' + pathsFrom['frame_high_uni']+ " " + pathsTo['frame_high_uni'] )
				shutil.copyfile( pathsFrom['frame_high_uni'] , pathsTo['frame_high_uni'] )

			frameNo += 1

	# copy sim done





