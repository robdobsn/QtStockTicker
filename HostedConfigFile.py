import ftplib
import requests
import tempfile
import json
import os
import sys

'''
Created on 07 Sep 2013

@author: rob dobson
'''

class HostedConfigFile():
    
    hostedDataLocations = []
    latestFileVersion = -1
    
    def initFromFile(self, fName):
        with open(fName, 'r') as jsonFile:
            localSetup = json.load(jsonFile)
            if localSetup != None and 'ConfigLocations' in localSetup:
                for locn in localSetup['ConfigLocations']:
                    self.hostedDataLocations.append(locn)
        
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
            fileVersion = -1
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
                    fileVersion = int(jsonData['FileVersion'])
            else:
                tmpFiles.append(None)
                temporaryFile.close()
            fileVersions.append(fileVersion)
            fileIdx += 1
        # Find latest file version
        latestVersion = -1
        latestFileIdx = -1
        for fileIdx in range(len(fileVersions)):
            if latestVersion < fileVersions[fileIdx]:
                latestVersion = fileVersions[fileIdx]
                latestFileIdx = fileIdx
        # Check if we failed to get a valid file from anywhere
        if latestFileIdx == -1:
            print("No valid file available")
            for tFile in tmpFiles:
                if tFile != None:
                    tFile.close()
            return None
        self.latestFileVersion = latestVersion
        # Write back to versions that are not latest
        for fileIdx in range(len(fileVersions)):
            if fileVersions[fileIdx] != -1:
                print("FileIdx", fileIdx, "Version", fileVersions[fileIdx])
            if latestVersion != fileVersions[fileIdx]:
                self.copyFileToLocation(self.hostedDataLocations[fileIdx], tmpFiles[latestFileIdx])
        # Get contents of latest file
        print("LatestFileIdx", latestFileIdx, "Version", latestVersion)
        tmpFiles[latestFileIdx].seek(0, os.SEEK_SET)
        returnData = tmpFiles[latestFileIdx].read()
        # Close all temporary files (which should delete them)
        for tFile in tmpFiles:
            if tFile != None:
                tFile.close()
        print("Success")
        return returnData
                
    def putConfigContentsToLocation(self, jsonStr):
        tempFile = tempfile.TemporaryFile('w+t', delete=True)
        tempFile.write(jsonStr)
        tempFile.seek(0)
        for fileIdx in range(len(self.hostedDataLocations)):
            reslt = self.copyFileToLocation(self.hostedDataLocations[fileIdx], tempFile)
            print("PutToLocationIdx", fileIdx, "Result", reslt)
        
    def getFileWithFTP(self, locn, outFile):
        try:
            ftp = ftplib.FTP(locn['hostURLForGet'])
            ftp.login(locn['userName'], locn['passWord'])
            ftp.retrbinary("RETR " + locn['filePathForGet'], outFile.write)
            ftp.close()
            print ("Got file via FTP {0}", locn['hostURLForGet'])
            return True
        except:
            print ("Failed to get from FTP {0}", locn['hostURLForGet'])
        return False
    
    def getFileWithHTTP(self, locn, outFile):
        reqFile = None
        try:
            reqFile = requests.get(locn['hostURLForGet'] + locn['filePathForGet'], auth=(locn['userName'], locn['passWord']), timeout=0.5)
        except requests.exceptions.ConnectionError:
            print ("HTTP ConnectionError")
        except requests.exceptions.HTTPError:
            print ("HTTPError")
        except requests.exceptions.URLRequired:
            print ("HTTP URLRequired")
        except requests.exceptions.TooManyRedirects:
            print ("HTTP TooManyRedirects")
        except requests.exceptions.Timeout:
            print ("HTTP Timeout")
        except requests.exceptions.RequestException:
            print ("HTTP requests error")
        if reqFile != None and reqFile.status_code == 200:
            print (reqFile.status_code)
            # Strip spurious newlines
            newText = "\r".join([s for s in reqFile.text.splitlines() if s.strip("\r\n")])
            print(newText)
            outFile.write(newText)
            return True
        return False

    def getLocalFile(self, locn, outFile):
        print ("Trying to get local file {0}", locn['hostURLForGet'] + locn['filePathForGet'])
        try:
            with open(locn['hostURLForGet'] + locn['filePathForGet'], "r") as inFile:
                print ("Got ok")
                return self.copyFileContents(inFile, outFile)
        except IOError as excp:
            print ("getLocalFile I/O error({0}): {1}".format(excp.errno, excp.strerror))
        except ValueError:
            print ("Could not convert data to an integer.")
        except:
            print ("Unexpected error:", sys.exc_info()[0])
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
            print ("copyFileContents I/O error({0}): {1}".format(excp.errno, excp.strerror))
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
            print("FTP error", str(excp))
            tempFile.close()
            return False
        tempFile.close()
        return True
    
    def copyFileToLocation(self, locn, fileToCopyFrom):
        success = False
        try:
            if locn['putUsing'] == 'ftp':
                print ("Attempting to copy file using ftp to ", locn['hostURLForPut'], locn['filePathForPut'])
                success = self.putFileWithFTP(locn, fileToCopyFrom)
            elif locn['putUsing'] == 'local':
                print ("Attempting to copy file local to ", locn['hostURLForPut'], locn['filePathForPut'])
                with open(locn['hostURLForPut'] + locn['filePathForPut'], "wt") as outFile:
                    success = self.copyFileContents(fileToCopyFrom, outFile)
        except:
            print("Failed to copy file")
        return success

    def configFileUpdate(self, updatedData):
        # form data to write
        updatedData["FileVersion"] = self.latestFileVersion + 1
        jsonStr = json.dumps(updatedData, indent=4)
        self.putConfigContentsToLocation(jsonStr)
        
