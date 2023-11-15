import ftplib
import requests
import tempfile
import json
import os
import sys
import logging

logger = logging.getLogger("StockTickerLogger")

'''
Created on 07 Sep 2013

@author: rob dobson
'''

class HostedConfigFile():
    
    hostedDataLocations = []
    latestFileVersion = -1
    
    def initFromFile(self, fName):
        try:
            with open(fName, 'r') as jsonFile:
                localSetup = json.load(jsonFile)
                if localSetup != None and 'ConfigLocations' in localSetup:
                    for locn in localSetup['ConfigLocations']:
                        self.hostedDataLocations.append(locn)
        except IOError as excp:
            logger.warn ("HostedConfigFile I/O error({0}): {1}".format(excp.errno, excp.strerror))
        except ValueError:
            logger.warn ("HostedConfigFile Could not convert data to an integer.")
        except:
            logger.error ("HostedConfigFile Unexpected error:", sys.exc_info()[0])
            raise
        
    def addDataLocation(self, hostURLForGet, filePathForGet, getUsing, hostURLForPut, filePathForPut, putUsing, userName, passWord):
        newLocation = { 'hostURLForGet': hostURLForGet, 'filePathForGet': filePathForGet, 'getUsing': getUsing, 
                       'hostURLForPut': hostURLForPut, 'filePathForPut': filePathForPut, 'putUsing': putUsing, 
                       'userName': userName, 'passWord':passWord }
        self.hostedDataLocations.append(newLocation)

    def getFileFromLocation(self, destFilePath):
        # Get config file contents
        configContents = self.getConfigContentsFromLocation()
        if configContents == None:
            return False
        # Copy best file to output
        with open(destFilePath, "wt") as outFile:
            outFile.write(configContents)
        return True

    def getConfigDataFromLocation(self):
        configContents = self.getConfigContentsFromLocation()
        if configContents == None:
            return None
        configData = json.loads(configContents)
        return configData

    def getConfigContentsFromLocation(self):
        # Work through the locations in order trying to get the file
        tmpFiles = []
        fileVersions = []
        fileIdx = 0
        for locn in self.hostedDataLocations:
            # Get temp file
            bFileLoadOk = False
            fileVersion = { "ver":-1, "source":"" }
            temporaryFile = tempfile.TemporaryFile('w+t', delete=True)
            if locn['getUsing'] == 'ftp':
                bFileLoadOk = self.getFileWithFTP(locn, temporaryFile)
            elif locn['getUsing'] == 'http': 
                bFileLoadOk = self.getFileWithHTTP(locn, temporaryFile)
            elif locn['getUsing'] == 'local':
                bFileLoadOk = self.getLocalFile(locn, temporaryFile)
            if bFileLoadOk:
                tmpFiles.append(temporaryFile)
                temporaryFile.seek(0)
                # Read the version info from the file
                jsonData = json.load(temporaryFile)
                if 'FileVersion' in jsonData:
                    fileVersion = {"ver":int(jsonData['FileVersion']), "source":(locn["sourceName"] if "sourceName" in locn else "")}
            else:
                tmpFiles.append(None)
                temporaryFile.close()
            fileVersions.append(fileVersion)
            fileIdx += 1
        # Find latest file version
        latestVersion = -1
        latestFileIdx = -1
        for fileIdx in range(len(fileVersions)):
            if latestVersion < fileVersions[fileIdx]["ver"]:
                latestVersion = fileVersions[fileIdx]["ver"]
                latestFileIdx = fileIdx
        # Check if we failed to get a valid file from anywhere
        if latestFileIdx == -1:
            logger.warn(f"No valid config file available from any source")
            for tFile in tmpFiles:
                if tFile != None:
                    tFile.close()
            return None
        self.latestFileVersion = latestVersion
        # Write back to versions that are not latest
        for fileIdx in range(len(fileVersions)):
            if fileVersions[fileIdx] != -1:
                logger.debug(f"FileIdx {fileIdx} Version {fileVersions[fileIdx]['ver']} Source {fileVersions[fileIdx]['source']}")
            if latestVersion != fileVersions[fileIdx]["ver"]:
                self.copyFileToLocation(self.hostedDataLocations[fileIdx], tmpFiles[latestFileIdx])
        # Get contents of latest file
        logger.debug(f"LatestFileIdx {latestFileIdx} Version {latestVersion}")
        tmpFiles[latestFileIdx].seek(0, os.SEEK_SET)
        returnData = tmpFiles[latestFileIdx].read()
        # Close all temporary files (which should delete them)
        for tFile in tmpFiles:
            if tFile != None:
                tFile.close()
        logger.debug(f"Got config file from {fileVersions[latestFileIdx]['source']}")
        return returnData
                
    def putConfigContentsToLocation(self, jsonStr):
        tempFile = tempfile.TemporaryFile('w+t', delete=True)
        tempFile.write(jsonStr)
        tempFile.seek(0)
        for fileIdx in range(len(self.hostedDataLocations)):
            reslt = self.copyFileToLocation(self.hostedDataLocations[fileIdx], tempFile)
            logger.debug(f"PutToLocationIdx {fileIdx} Result {reslt}")
        
    def getFileWithFTP(self, locn, outFile):
        try:
            ftp = ftplib.FTP(locn['hostURLForGet'])
            ftp.login(locn['userName'], locn['passWord'])
            # ftp.dir()
            for filename in ftp.nlst(locn['filePathForGet']):
                logger.debug(f"Getting FTP file {filename}")
                ftp.retrlines('RETR ' + filename, outFile.write)
                break
            ftp.close()
            logger.debug(f"Got file via FTP {locn['hostURLForGet']}")
            return True
        except Exception as excp:
            logger.warn(f"Failed to get from FTP {locn['hostURLForGet']} excp {excp}")
        return False
    
    def getFileWithHTTP(self, locn, outFile):
        reqFile = None
        fullPath = locn['hostURLForGet'] + locn['filePathForGet']
        try:
            reqFile = requests.get(fullPath, auth=(locn['userName'], locn['passWord']), timeout=30)
        except requests.exceptions.ConnectionError:
            logger.warn(f"HTTP ConnectionError {fullPath}")
        except requests.exceptions.HTTPError:
            logger.warn(f"HTTPError {fullPath}")
        except requests.exceptions.URLRequired:
            logger.warn(f"HTTP URLRequired {fullPath}")
        except requests.exceptions.TooManyRedirects:
            logger.warn(f"HTTP TooManyRedirects {fullPath}")
        except requests.exceptions.Timeout:
            logger.warn(f"HTTP Timeout {fullPath}")
        except requests.exceptions.RequestException:
            logger.warn(f"HTTP requests error {fullPath}")
        if reqFile != None and reqFile.status_code == 200:
            logger.debug(f"Got file via HTTP {fullPath} status {reqFile.status_code}")
            # Strip spurious newlines
            newText = "\r".join([s for s in reqFile.text.splitlines() if s.strip("\r\n")])
            # logger.debug(f"Got file via HTTP {fullPath} text {newText}")
            outFile.write(newText)
            return True
        return False

    def getLocalFile(self, locn, outFile):
        logger.debug(f"Trying to get local file {locn['hostURLForGet'] + locn['filePathForGet']}")
        try:
            with open(locn['hostURLForGet'] + locn['filePathForGet'], "r") as inFile:
                logger.debug(f"Got local file {locn['hostURLForGet'] + locn['filePathForGet']}")
                return self.copyFileContents(inFile, outFile)
        except IOError as excp:
            logger.warn (f"getLocalFile I/O error({excp.errno}): {excp.strerror}")
        except ValueError:
            logger.warn ("getLocalFile Could not convert data to an integer.")
        except:
            logger.error ("getLocalFile Unexpected error:", sys.exc_info()[0])
            raise
        return False

    def copyFileContents(self, inFile, outFile):
        try:
            inFile.seek(0)
            while(True):
                linStr = inFile.readline()
                if linStr == '':
                    break
                outFile.write(linStr)
        except IOError as excp:
            logger.error(f"copyFileContents I/O error({excp.errno}): {excp.strerror}")
        except:
            return False
        return True
    
    def putFileWithFTP(self,locn,inFile):
        inFile.seek(0)
        tempFile = tempfile.TemporaryFile('w+b', delete=True)
        while(True):
            linStr = inFile.readline()
            if linStr == '':
                break
            tempFile.write(linStr.encode('ascii'))
        tempFile.seek(0)
        try:
            with ftplib.FTP(locn['hostURLForPut']) as ftp:
                ftp.login(locn['userName'], locn['passWord'])
                fileNameParts = os.path.split(locn['filePathForPut'])
                ftp.cwd(fileNameParts[0])
                ftp.storbinary("STOR " + fileNameParts[1], tempFile)
        except ftplib.all_errors as excp:
            logger.warn("FTP error", str(excp))
            tempFile.close()
            return False
        tempFile.close()
        return True
    
    def copyFileToLocation(self, locn, fileToCopyFrom):
        success = False
        try:
            if locn['putUsing'] == 'ftp':
                logger.debug(f"Attempting to copy file using ftp to {locn['hostURLForPut']} {locn['filePathForPut']}")
                success = self.putFileWithFTP(locn, fileToCopyFrom)
            elif locn['putUsing'] == 'local':
                logger.debug(f"Attempting to copy file local to {locn['hostURLForPut']} {locn['filePathForPut']}")
                with open(locn['hostURLForPut'] + locn['filePathForPut'], "wt") as outFile:
                    success = self.copyFileContents(fileToCopyFrom, outFile)
        except:
            logger.warn(f"Failed to copy file to {locn['hostURLForPut']} {locn['filePathForPut']}")
        return success

    def configFileUpdate(self, updatedData):
        # form data to write
        updatedData["FileVersion"] = self.latestFileVersion + 1
        jsonStr = json.dumps(updatedData, indent=4)
        self.putConfigContentsToLocation(jsonStr)
