# ############################################################################
# 
# This software is made freely available in accordance with the simplifed BSD
# license:
# 
# Copyright (c) <2018>, <Stephen McMahon>
# All rights reserved
# Redistribution and use in source and binary forms, with or without 
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, 
# this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation 
# and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND ANY 
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED 
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE 
# DISCLAIMED. IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES 
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; 
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND 
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT 
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF 
# THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Contacts: Stephen McMahon,	stephen.mcmahon@qub.ac.uk
# 
# ############################################################################
import random
import math
import numpy as np

from . import chromModel
from . import trackModel
from . import SDDWriter

# Declare a bunch of constants
# # For proton, PDG code is 2212
# # For photon, PDG code is 22
DSBRate = 1.0
DSBComplexity = 0.43
directFrac = 0.4
DSBPerGy = 35

# Reference target radius for human cells, to calculate DNA density
refTargRadius=4.32

# Should we use the sparse SDD format?
writeSparse=True

# Little handler to convert a list to comma separated string
def toCSV(A,sep=','):
	return sep.join(map(str,A))

# Return model damage string
def generateDmgandBase(damageType):
	fullBreakType = [0,0,0]

	damageArray = [[0*n for n in range(20)] for m in range(4)]
	# Single SSB
	if damageType==[0,1,0]:
		strand = random.choice([0,3])
		damageArray[strand][0]=1
		fullBreakType[1]+=1

	# Single DSB, losing 1 to 1 bases
	if damageType==[0,0,1]:
		breakLength = random.randint(1,1)
		# Single bp break is one column
		if breakLength==1:
			for row in range(4):
				damageArray[row][0]=1
		else:
			# Multi-BP break is marked by start and end
			for row in range(4):
				for position in range(breakLength):
					damageArray[row][0]=1
					damageArray[row][position+1]=1

		fullBreakType[0]+=breakLength*2
		fullBreakType[1]+=breakLength*2
		fullBreakType[2]+=1

	# DSB+SSB within 10 BP
	if damageType==[0,1,1]:
		SSBGap = random.randint(-10,10)
		SSBStrand = random.choice([0,3])
		breakLength = random.randint(1,4)

		if SSBGap<0:
			SSB_BP = 0
			DSB_Start = -SSBGap
		else:
			SSB_BP = SSBGap+breakLength
			DSB_Start = 0

		damageArray[SSBStrand][SSB_BP]=1
		fullBreakType[1]+=1

		if breakLength==1:
			for row in range(4):
				damageArray[row][DSB_Start]=1
		else:
			# Fill in all parts of a multi-BP entry
			for row in range(4):
				for position in range(breakLength):
					damageArray[row][DSB_Start+position]=1

		fullBreakType[0]+=breakLength*2
		fullBreakType[1]+=breakLength*2
		fullBreakType[2]+=1

	# Print out data. Row by row, left to right. 
	damageString = ''
	for row in range(4):
		for col in range(len(damageArray[row])):
			if damageArray[row][col]>0:
				damageString=damageString+' '.join(map(str,[row+1,col+1,damageArray[row][col]]))+'/'

	# Generate DNA bases string
	bases = [random.randint(1,4) for n in range(len(damageArray[0]))]

	# Remove single deletions
	for base in range(len(damageArray[0])):
		if damageArray[1][base]==1:
			bases[base]=0

	baseString = ''.join(map(str,bases))

	return damageString,baseString,fullBreakType

# Generate a damage uniformly distributed within cell
def XRayHits(DSBCount = 1.0,radius=1.0):
	# Poisson distribute around mean count number
	targetDSBs = np.random.poisson(DSBCount)
	# Also assign SSBs if calculating
	if DSBRate<1.0:
		SSBScaling = (1-DSBRate)/DSBRate
		targetSSBs = max(1,np.random.poisson(DSBCount/SSBScaling))
	else:
		targetSSBs = 0
	breakCounts = [targetSSBs,targetDSBs]

	# For each break, generate X,Y, Z positon randomly
	retBreaks = []
	for comp,breaks in enumerate(breakCounts):
		for n in range(breaks):
			phi = 2*math.pi*random.random()
			theta = math.acos(random.uniform(-1,1))
			u = random.random()

			r = radius*pow(u,1.0/3.0)

			x = r*math.sin(theta)*math.cos(phi)
			y = r*math.sin(theta)*math.sin(phi)
			z = r*math.cos(theta)
			retBreaks.append( [x,y,z,comp,1] )
	return retBreaks

# Generate damage distributed around an ion track
def ionHits(DSBCount=1.0,radius=1.0,LETdata=None,EPerDSB=60.1, fixedTracks=None, breakStats=False):
	# If LET is 0, fall back to uniform X-ray distribution
	LET, radialData, energy, EScaling = LETdata
	if LET==0:
		return XRayHits(DSBCount,radius)

	# Calculate hits per track, and number of tracks
	EPerDSB = EPerDSB*EScaling
	DSBPerTrack = (LET/EPerDSB)*(2.0*radius)

	trackEstimate = DSBCount/(DSBPerTrack*2.0/3.0)
	if fixedTracks is None:
		actualTracks = np.random.poisson(trackEstimate)
	else:
		actualTracks = fixedTracks

	# Generate damage by track
	retBreaks = []
	coreBreaks = 0
	rList = []		
	for m in range(actualTracks):
		newEvent = 1

		# Calculate X,Y position where track arrives
		u = random.random()
		r = radius*pow(u,1.0/2.0)
		phi = 2*math.pi*random.random()
		X = r*math.cos(phi)
		Y = r*math.sin(phi)

		# Calculate actual DSB and SSB by this track
		trackDSBs = np.random.poisson(DSBPerTrack)
		if DSBRate<1.0:
			SSBScaling = (1-DSBRate)/DSBRate
			trackSSBs = np.random.poisson(DSBCount/SSBScaling)
		else:
			trackSSBs = 0
		breakCounts = [trackSSBs,trackDSBs]

		# For each break, position randomly along track length, and sample radial position from
		# track data file.
		for comp,breaks in enumerate(breakCounts):
			for n in range(breaks):
				zPos = 2*(0.5-np.random.uniform())*radius

				radialFrac = np.random.uniform()
				dr = trackModel.sampleRadialPos(radialFrac,radialData)

				dPhi = 2*math.pi*random.random()
				xPos = X+dr*math.cos(dPhi)
				yPos = Y+dr*math.sin(dPhi)

				# Make sure that sampled hit actually remains within the nucleus
				if xPos*xPos + yPos*yPos + zPos*zPos < radius*radius:
					retBreaks.append([xPos,yPos,zPos,comp,newEvent])
					newEvent = 0
					rList.append(dr)
					if dr<0.05:
						coreBreaks+=1

	# Print some statistics about break radial positions if requested
	if breakStats:
		print(LET, LET/EPerDSB, actualTracks, len(retBreaks), coreBreaks, end=' ')
		print('\t'.join(map(str,(len([x for x in rList if x>r and x<r+0.0025])*1.0/len(rList) 
			                          for r in np.arange(0,4,0.0025)))))
	return retBreaks

# Generate hits for a given exposure
def generateHits(runs, radius=1.0, DSBCount=1, chromosomes=1, 
			     bdRange=-1, letData=None, particleTypes="2212"):
	# Generate chromosome model
	chromModel.subDivideSphere(chromosomes,radius)
	hitList = []
	eventNo = 0

	# Iterate over number of repeats
	for n in range(runs):
		hitList.append([])
		breakPositions = ionHits(DSBCount, radius, letData)

		# For each position, generate break characteristics
		for pos in breakPositions:
			x,y,z,c,newEvent = pos

			# Increment counter if it's a new event
			if newEvent>0: eventNo+=1

			# If hit list is empty, this is a new exposure
			if hitList[-1]==[]:
				newEvent = 2
				eventNo = 0 #Reset to zero for new exposure

			# Build 3D break extent
			breakExtent = [x,y,z,x+0.01,y+0.01,z+0.01,x-0.01,y-0.01,z-0.01]

			# Set break type
			if c==0:
				breakType = [0,1,0]
			else:
				if random.random()>DSBComplexity:
					breakType = [0,0,1]
				else:
					breakType = [0,1,1]

			# Set cause through random assignment
			if random.random()>directFrac:
				cause = 1
			else:
				cause = 0

			# Sample chromosome, and generate illustrative damage structure
			chromID, chromPos = chromModel.modelChromosome(x,y,z)
			damageString,baseString,fullBreakType = generateDmgandBase(breakType)

			# Set BDs to 0 if we're not logging those
			if bdRange<0: fullBreakType[0]=0

			# Placeholder values for other parameters if a full output is requested
			time = str(random.random()*2.0)
			energies = letData[2]
			trans = [x,y,-5]
			direction = [0,0,0]
			pTime = 0

			# Append hit data, either in minimal or comprehensive format
			if writeSparse:
				hitList[-1].append([toCSV([newEvent,eventNo],','), toCSV([x,y,z],', '), 
									toCSV(fullBreakType)])
			else:
				hitList[-1].append([toCSV([newEvent,eventNo],','),toCSV(breakExtent,', '), chromID, 
					                chromPos, cause, toCSV(fullBreakType), damageString, baseString,
					                time, particleTypes, energies, toCSV(trans,'/'), 
					                toCSV(direction,'/'), pTime])
	return hitList

# Generate hits for a requested exposure, and write this data to an SDD-formatted file
def simExposure(hits, runs, chromosomes, outFile, targetVol, geometry=[1,3,3,3], DNADensity=-1,
	            bdRange=-1, O2=-1, incident="22", energy=0.1, function="Point", 
	            grouping="Single Event", letData=None):
	hitData = generateHits(runs, geometry[1], hits, chromosomes, bdRange, 
						   letData, particleTypes=incident)
	SDDWriter.writeToFile(hitData, outFile, writeSparse, targetVol, geometry, DNADensity, bdRange,
						  O2, incident, energy, hits/DSBPerGy, function, grouping)

# Generate PID for different particle types, based on atomic number (Z=0 is gamma)
def PIDLookup(Z):
	if Z==0:
		return '22'
	if Z==1:
		return '2212'
	if Z>1:
		# Base string - nucleus with 0 strange quarks
		baseString = '100'
		zVal = str(Z)
		while len(zVal)<3: zVal = '0'+zVal
		aVal = str(2*Z)
		while len(aVal)<3: aVal = '0'+aVal

		return baseString+zVal+aVal+'0'

# Look up appropriate datafile, if available. Fall back to Carbon if non-supported ion is requested
def dataFileNames(Z):
	particleNames = ['Gamma', 'Proton', 'Helium', 'Lithium', 'Beryllium', 'Boron', 'Carbon', 
					 'Nitrogen', 'Oxygen']
	if Z==1 or Z==2 or Z==6 or Z==7:
		return 'Radial Energy '+particleNames[Z]+'.xlsx'
	else:
		return 'Radial Energy Carbon.xlsx'

# Generate an exposure for a requested ion, LET, and number of repeats
def generateExposure(energy, LET, dose, particleZ, runs, targetRadius=4.32, 
				     chromosomes=46, extraTargetInfo=''):
	# Some general model parameters for SDD header
	DNADensity = 6100/(4.0/3.0*math.pi*pow(refTargRadius,3))
	geometry = [1,targetRadius,targetRadius,targetRadius]
	targetVol = str(targetRadius)+' um spherical nucleus'
	particleID = PIDLookup(particleZ)
	bdRange = -1 # Don't record base damages

	# Set up output file name
	# Calculate hits by scaling by dose
	hits = dose*DSBPerGy
	#if hits%DSBPerGy == 0:
	#	dose = str(hits/DSBPerGy)
	#else:
#		dose = str(round(hits/DSBPerGy,2))
	fileBase = 'DNA Damage Z='+str(particleZ)+ ' '
	fileName = fileBase+str(energy)+' MeV '+ str(dose) + ' Gy'
	if writeSparse:
		fileName = fileName + ' minimal.txt'
	else:
		fileName = fileName + ' full.txt'

	# Get track data for model input
	letData = None
	if particleZ>0:
		trackFile = dataFileNames(particleZ)
		trackModel.readCumuDoseFile(trackFile)
		letData = [LET, trackModel.buildCumCurve(LET), energy, pow(targetRadius/refTargRadius,3)]
	else:
		letData = [0,None,energy,pow(targetRadius/refTargRadius,3)]



	# Run simulation
	print(energy, LET, hits)
	simExposure(hits, runs, chromosomes, fileName, targetVol, geometry, DNADensity, bdRange,
				letData=letData, incident=particleID, energy=energy)

# Build a basic X-ray and ion dataset
def basicXandIon(targetRadius = 4.32, runs = 10, conditions=None, extraTargetInfo = ''):
	# Photons, doses from 1 to 8 Gy
	particleZ = 0
	ionConditions = [[1.0,0,1], [1.0,0,2], [1.0,0,3], [1.0,0,4], 
					 [1.0,0,6], [1.0,0,8]]
	for energy, LET, dose in ionConditions:
		generateExposure(energy, LET, dose, particleZ, runs, targetRadius, chromosomes=46)

	# Protons, at a dose of 1 Gy 
	particleZ = 1 
	ionConditions = [ [0.975,29.78,1], [1.175,25.27,1], [1.5,20.59,1], 
				      [1.8, 17.78, 1], [2.2,15.19,1],   [2.5,13.72,1], 
				      [3.5, 10.60, 1], [5.5,7.42,1],    [8.5,5.25,1], 
				      [34,  1.77,  1] ]
	for energy, LET, dose in ionConditions:
		generateExposure(energy, LET, dose, particleZ, runs, targetRadius, chromosomes=46)

	# Carbon ions, at a dose of 1 Gy
	particleZ = 6
	ionConditions = [ [24,512,    1], [60,265,1], [120,151.95,1],
					  [185,100,   1], [360,60,1], [960,26,1],
					  [1200,20.29,1] ]
	for energy, LET, dose in ionConditions:
		generateExposure(energy, LET, dose, particleZ, runs, targetRadius, chromosomes=46)
		