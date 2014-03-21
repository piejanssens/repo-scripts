# -*- coding: utf-8 -*-
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with XBMC; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# *
import sys
import os
import re
import random
import traceback
import xml.etree.ElementTree as ET
#Modules XBMC
import xbmcplugin
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon

# Add JSON support for queries
if sys.version_info < (2, 7):
    import simplejson
else:
    import json as simplejson


__addon__     = xbmcaddon.Addon(id='script.videoextras')
__addonid__   = __addon__.getAddonInfo('id')
__cwd__       = __addon__.getAddonInfo('path').decode("utf-8")
__resource__  = xbmc.translatePath( os.path.join( __cwd__, 'resources' ).encode("utf-8") ).decode("utf-8")
__lib__  = xbmc.translatePath( os.path.join( __resource__, 'lib' ).encode("utf-8") ).decode("utf-8")

sys.path.append(__resource__)
sys.path.append(__lib__)

# Import the common settings
from settings import Settings
from settings import log
from settings import os_path_join

# Load the database interface
from database import ExtrasDB

from VideoParser import VideoParser



###############################################################
# Class to make it easier to see which screen is being checked
###############################################################
class WindowShowing():
    xbmcMajorVersion = 0

    @staticmethod
    def getXbmcMajorVersion():
        if WindowShowing.xbmcMajorVersion == 0:
            xbmcVer = xbmc.getInfoLabel('system.buildversion')
            log("WindowShowing: XBMC Version = %s" % xbmcVer)
            WindowShowing.xbmcMajorVersion = 12
            try:
                # Get just the major version number
                WindowShowing.xbmcMajorVersion = int(xbmcVer.split(".", 1)[0])
            except:
                # Default to frodo as the default version if we fail to find it
                log("WindowShowing: Failed to get XBMC version")
            log("WindowShowing: XBMC Version %d (%s)" % (WindowShowing.xbmcMajorVersion, xbmcVer))
        return WindowShowing.xbmcMajorVersion

    @staticmethod
    def isTv():
        if xbmc.getCondVisibility("Container.Content(tvshows)"):
            return True
        if xbmc.getCondVisibility("Container.Content(Seasons)"):
            return True
        if xbmc.getCondVisibility("Container.Content(Episodes)"):
            return True
        
        folderPathId = "videodb://2/2/"
        # The ID for the TV Show Title changed in Gotham
        if WindowShowing.getXbmcMajorVersion() > 12:
            folderPathId = "videodb://tvshows/titles/"
        if xbmc.getInfoLabel( "container.folderpath" ) == folderPathId:
            return True # TvShowTitles

        return False


########################################################
# Class to store all the details for a given extras file
########################################################
class BaseExtrasItem():
    def __init__( self, directory, filename, isFileMatchExtra=False ):
        self.directory = directory
        self.filename = filename
        # Setup the icon and thumbnail images
        self.thumbnailImage = ""
        self.iconImage = ""
        self.fanart = ""
        self._loadImages(filename)

        self.duration = None

        # Record if the match was by filename rather than in Extras sub-directory
        self.isFileMatchingExtra = isFileMatchExtra
        # Check if there is an NFO file to process
        if not self._loadNfoInfo(filename):
            # Get the ordering and display details from the filename
            (self.orderKey, self.displayName) = self._generateOrderAndDisplay(filename)

    # eq and lt defined for sorting order only
    def __eq__(self, other):
        if other == None:
            return False
        # Check key, display then filename - all need to be the same for equals
        return ((self.orderKey, self.displayName, self.directory, self.filename, self.isFileMatchingExtra) ==
                (other.orderKey, other.displayName, other.directory, other.filename, other.isFileMatchingExtra))

    def __lt__(self, other):
        # Order in key, display then filename 
        return ((self.orderKey, self.displayName, self.directory, self.filename, self.isFileMatchingExtra) <
                (other.orderKey, other.displayName, other.directory, other.filename, other.isFileMatchingExtra))

    # Returns the name to display to the user for the file
    def getDisplayName(self):
        # Update the display name to allow for : in the name
        return self.displayName.replace(".sample","").replace("&#58;", ":")

    # Return the filename for the extra
    def getFilename(self):
        return self.filename

    # Gets the file that needs to be passed to the player
    def getMediaFilename(self):
        # Check to see if the filename actually holds a directory
        # If that is the case, we will only support it being a DVD Directory Image
        # So check to see if the expected file is set
        vobFile = self.getVOBFile()
        if vobFile != None:
            return vobFile
        
        return self.filename

    # Gets the path to the VOB playable file, or None if not a VOB
    def getVOBFile(self):
        # Check to see if the filename actually holds a directory
        # If that is the case, we will only support it being a DVD Directory Image
        # So check to see if the expected file is set
        videoTSDir = os_path_join( self.filename, 'VIDEO_TS' )
        if xbmcvfs.exists(videoTSDir):
            ifoFile = os_path_join( videoTSDir, 'VIDEO_TS.IFO' )
            if xbmcvfs.exists( ifoFile ):
                return ifoFile
        # Also check for BluRay
        videoBluRayDir = os_path_join( self.filename, 'BDMV' )
        if xbmcvfs.exists(videoBluRayDir):
            dbmvFile = os_path_join( videoBluRayDir, 'index.bdmv' )
            if xbmcvfs.exists( dbmvFile ):
                return dbmvFile
        return None

    # Compare if a filename matches the existing one
    def isFilenameMatch(self, compareToFilename):
        srcFilename = self.filename
        tgtFilename = compareToFilename
        try:
            srcFilename = srcFilename.decode("utf-8")
        except:
            pass
        try:
            tgtFilename = tgtFilename.decode("utf-8")
        except:
            pass
        if srcFilename == tgtFilename:
            return True
        return False

    def getDirectory(self):
        return self.directory

    def isFileMatchExtra(self):
        return self.isFileMatchingExtra
    
    def getOrderKey(self):
        return self.orderKey

    def getThumbnailImage(self):
        return self.thumbnailImage

    def getIconImage(self):
        return self.iconImage

    def getFanArt(self):
        if self.fanart == "":
            self.fanart = SourceDetails.getFanArt()
        return self.fanart

    # Returns the duration in seconds
    def getDuration(self):
        if self.duration == None:
            try:
                # Parse the video file for the duration
                self.duration = VideoParser().getVideoLength(self.filename)
                log("BaseExtrasItem: Duration retrieved is = %d" % self.duration)
            except:
                log("BaseExtrasItem: Failed to get duration from %s" % self.filename)
                log("BaseExtrasItem: %s" % traceback.format_exc())
                self.duration = 0
        
        return self.duration

    def getDisplayDuration(self, forcedDuration=0):
        durationInt = forcedDuration
        if forcedDuration < 1:
            durationInt = self.getDuration()

        displayDuration = ""
        seconds = 0
        minutes = 0
        hours = 0

        # Convert the duration into a viewable format
        if durationInt > 0:
            seconds = durationInt % 60
 
            if durationInt > 60:
                minutes = ((durationInt - seconds) % 3600)/60

            # Default the display to MM:SS
            displayDuration = "%02d:%02d" % (minutes, seconds)

            # Only add the hours is really needed
            if durationInt > 3600:
                hours = (durationInt - (minutes*60) - seconds)/3600
                displayDuration = "%02d:%s" % (hours, displayDuration)

        # Set the display duration to be the time in minutes
        return displayDuration
        

    # Load the Correct set of images for icons and thumbnails
    # Image options are
    # (NFO - Will overwrite these values)
    # <filename>.tbn/jpg
    # <filename>-poster.jpg (Auto picked up by player)
    # <filename>-thumb.jpg
    # poster.jpg
    # folder.jpg
    #
    # See:
    # http://wiki.xbmc.org/?title=Thumbnails
    # http://wiki.xbmc.org/index.php?title=Frodo_FAQ#Local_images
    def _loadImages(self, filename):
        imageList = []
        # Find out the name of the image files
        fileNoExt = os.path.splitext( filename )[0]

        # Start by searching for the filename match
        fileNoExtImage = self._loadImageFile( fileNoExt )
        if fileNoExtImage != "":
            imageList.append(fileNoExtImage)

        # Check for -poster added to the end
        fileNoExtImage = self._loadImageFile( fileNoExt + "-poster" )
        if fileNoExtImage != "":
            imageList.append(fileNoExtImage)

        if len(imageList) < 2:
            # Check for -thumb added to the end
            fileNoExtImage = self._loadImageFile( fileNoExt + "-thumb" )
            if fileNoExtImage != "":
                imageList.append(fileNoExtImage)

        if len(imageList) < 2:
            # Check for poster.jpg
            fileDir = os_path_join(self.directory, "poster")
            fileNoExtImage = self._loadImageFile( fileDir )
            if fileNoExtImage != "":
                imageList.append(fileNoExtImage)

        if len(imageList) < 2:
            # Check for folder.jpg
            fileDir = os_path_join(self.directory, "folder")
            fileNoExtImage = self._loadImageFile( fileDir )
            if fileNoExtImage != "":
                imageList.append(fileNoExtImage)
                
        # Set the first one to the thumbnail, and the second the the icon
        if len(imageList) > 0:
            self.thumbnailImage = imageList[0]
            if len(imageList) > 1:
                self.iconImage = imageList[1]

        # Now check for the fanart
        # Check for -fanart added to the end
        fileNoExtImage = self._loadImageFile( fileNoExt + "-fanart" )
        if fileNoExtImage != "":
            self.fanart = fileNoExtImage
        else:
            # Check for fanart.jpg
            fileDir = os_path_join(self.directory, "fanart")
            fileNoExtImage = self._loadImageFile( fileDir )
            if fileNoExtImage != "":
                self.fanart = fileNoExtImage


    # Searched for a given image name under different extensions
    def _loadImageFile(self, fileNoExt):
        if xbmcvfs.exists( fileNoExt + ".tbn" ):
            return fileNoExt + ".tbn"
        if xbmcvfs.exists( fileNoExt + ".png" ):
            return fileNoExt + ".png"
        if xbmcvfs.exists( fileNoExt + ".jpg" ):
            return fileNoExt + ".jpg"
        return ""

    # Parses the filename to work out the display name and order key
    def _generateOrderAndDisplay(self, filename):
        # First thing is to trim the display name from the filename
        # Get just the filename, don't need the full path
        displayName = os.path.split(filename)[1]
        # Remove the file extension (e.g .avi)
        displayName = os.path.splitext( displayName )[0]
        # Remove anything before the -extras- tag (if it exists)
        extrasTag = Settings.getExtrasFileTag()
        if (extrasTag != "") and (extrasTag in displayName):
            justDescription = displayName.split(extrasTag,1)[1]
            if len(justDescription) > 0:
                displayName = justDescription
        
        result = ( displayName, displayName )
        # Search for the order which will be written as [n]
        # Followed by the display name
        match = re.search("^\[(?P<order>.+)\](?P<Display>.*)", displayName)
        if match:
            orderKey = match.group('order')
            if orderKey != "":
                result = ( orderKey, match.group('Display') )
        return result

    # Check for an NFO file for this video and reads details out of it
    # if it exists
    def _loadNfoInfo(self, filename):
        # Find out the name of the NFO file
        nfoFileName = os.path.splitext( filename )[0] + ".nfo"
        
        log("BaseExtrasItem: Searching for NFO file: %s" % nfoFileName)
        
        # Return False if file does not exist
        if not xbmcvfs.exists( nfoFileName ):
            log("BaseExtrasItem: No NFO file found: %s" % nfoFileName)
            return False

        returnValue = False

        try:
            # Need to first load the contents of the NFO file into
            # a string, this is because the XML File Parse option will
            # not handle formats like smb://
            nfoFile = xbmcvfs.File(nfoFileName, 'r')
            nfoFileStr = nfoFile.read()
            nfoFile.close()

            # Create an XML parser
            try:
                nfoXml = ET.ElementTree(ET.fromstring(nfoFileStr))
            except:
                log("BaseExtrasItem: Trying encoding to UTF-8 with ignore")
                nfoXml = ET.ElementTree(ET.fromstring(nfoFileStr.decode("UTF-8", 'ignore')))

            rootElement = nfoXml.getroot()
            
            log("BaseExtrasItem: Root element is = %s" % rootElement.tag)
            
            # Check which format if being used
            if rootElement.tag == "movie":
                log("BaseExtrasItem: Movie format NFO detected")
                #    <movie>
                #        <title>Who knows</title>
                #        <sorttitle>Who knows 1</sorttitle>
                #    </movie>
                
                # Get the title
                self.displayName = nfoXml.findtext('title')
                # Get the sort key
                self.orderKey = nfoXml.findtext('sorttitle')
    
            elif rootElement.tag == "tvshow":
                log("BaseExtrasItem: TvShow format NFO detected")
                #    <tvshow>
                #        <title>Who knows</title>
                #        <sorttitle>Who knows 1</sorttitle>
                #    </tvshow>
    
                # Get the title
                self.displayName = nfoXml.findtext('title')
                # Get the sort key
                self.orderKey = nfoXml.findtext('sorttitle')
    
            elif rootElement.tag == "episodedetails":
                log("BaseExtrasItem: TvEpisode format NFO detected")
                #    <episodedetails>
                #        <title>Who knows</title>
                #        <season>2</season>
                #        <episode>1</episode>
                #    </episodedetails>
    
                # Get the title
                self.displayName = nfoXml.findtext('title')
                # Get the sort key
                season = nfoXml.findtext('season')
                episode = nfoXml.findtext('episode')
                
                # Need to use the season and episode to order the list
                if (season == None) or (season == ""):
                    season = "0"
                if (episode == None) or (episode == ""):
                    episode = "0"
                self.orderKey = "%02d_%02d" % (int(season), int(episode))

            else:
                self.displayName = None
                self.orderKey = None
                log("BaseExtrasItem: Unknown NFO format")
    
            # Now get the thumbnail - always called the same regardless of
            # movie of TV
            thumbnail = self._getNfoThumb(nfoXml)
            if thumbnail != None:
                self.thumbnailImage = thumbnail

            # Now get the fanart - always called the same regardless of
            # movie of TV
            fanart = self._getNfoFanart(nfoXml)
            if fanart != None:
                self.fanart = fanart
    
            del nfoXml

            if (self.displayName != None) and (self.displayName != ""):
                returnValue = True
                # If there is no order specified, use the display name
                if (self.orderKey == None) or (self.orderKey == ""):
                    self.orderKey = self.displayName
                log("BaseExtrasItem: Using sort key %s for %s" % (self.orderKey, self.displayName))
        except:
            log("BaseExtrasItem: Failed to process NFO: %s" % nfoFileName)
            log("BaseExtrasItem: %s" % traceback.format_exc())
            returnValue = False

        return returnValue

    # Sets the title for a given extras file
    def setTitle(self, newTitle):
        log("BaseExtrasItem: Setting title to %s" % newTitle)
        self.displayName = newTitle

        # Find out the name of the NFO file
        nfoFileName = os.path.splitext( self.filename )[0] + ".nfo"
        
        log("BaseExtrasItem: Searching for NFO file: %s" % nfoFileName)
                
        try:
            nfoFileStr = None
            newNfoRequired = False
            
            if xbmcvfs.exists( nfoFileName ):
                # Need to first load the contents of the NFO file into
                # a string, this is because the XML File Parse option will
                # not handle formats like smb://
                nfoFile = xbmcvfs.File(nfoFileName, 'r')
                nfoFileStr = nfoFile.read()
                nfoFile.close()
    
            # Check to ensure we have some NFO data
            if (nfoFileStr == None) or (nfoFileStr == ""):
                # Create a default NFO File
                # Need to create a new file if one does not exist
                log("BaseExtrasItem: No NFO file found, creating new one: %s" % nfoFileName)
                tagType = 'movie'
                if SourceDetails.getTvShowTitle() != "":
                    tagType = 'tvshow'

                nfoFileStr = ("<%s>\n    <title> </title>\n</%s>\n" % (tagType, tagType))
                newNfoRequired = True
                
                
            # Create an XML parser
            try:
                nfoXml = ET.ElementTree(ET.fromstring(nfoFileStr))
            except:
                log("BaseExtrasItem: Trying encoding to UTF-8 with ignore")
                nfoXml = ET.ElementTree(ET.fromstring(nfoFileStr.decode("UTF-8", 'ignore')))

            # Get the title element
            titleElement = nfoXml.find('title')

            # Make sure the title exists in the file            
            if titleElement == None:
                log("BaseExtrasItem: title element not found")
                return False

            # Set the title to the new value
            titleElement.text = newTitle

            # Only set the sort title if already set
            sorttitleElement = nfoXml.find('sorttitle')
            if sorttitleElement != None:
                sorttitleElement.text = newTitle
            
            # Save the file back to the filesystem
            newNfoContent = ET.tostring(nfoXml.getroot(), encoding="UTF-8")
            del nfoXml
            
            nfoFile = xbmcvfs.File(nfoFileName, 'w')
            try:
                nfoFile.write(newNfoContent)
            except:
                log("BaseExtrasItem: Failed to write NFO: %s" % nfoFileName)
                log("BaseExtrasItem: %s" % traceback.format_exc())
                # Make sure we close the file handle
                nfoFile.close()
                # If there was no file before, make sure we delete and partial file
                if newNfoRequired:
                    xbmcvfs.delete(nfoFileName)
                return False
            nfoFile.close()

        except:
            log("BaseExtrasItem: Failed to write NFO: %s" % nfoFileName)
            log("BaseExtrasItem: %s" % traceback.format_exc())
            return False
        
        return True

        

    # Reads the thumbnail information from an NFO file
    def _getNfoThumb(self, nfoXml):
        # Get the thumbnail
        thumbnail = nfoXml.findtext('thumb')
        if (thumbnail != None) and (thumbnail != ""):
            # Found the thumb entry, check if this is a local path
            # which just has a filename, this is the case if there are
            # no forward slashes and no back slashes
            if (not "/" in thumbnail) and (not "\\" in thumbnail):
                thumbnail = os_path_join(self.directory, thumbnail)
        else:
            thumbnail = None
        return thumbnail

    # Reads the fanart information from an NFO file
    def _getNfoFanart(self, nfoXml):
        # Get the fanart
        fanart = nfoXml.findtext('fanart')
        if (fanart != None) and (fanart != ""):
            # Found the fanart entry, check if this is a local path
            # which just has a filename, this is the case if there are
            # no forward slashes and no back slashes
            if (not "/" in fanart) and (not "\\" in fanart):
                fanart = os_path_join(self.directory, fanart)
        else:
            fanart = None
        return fanart


####################################################################
# Extras item that extends the base type to supply extra information
# that can be read or set via a database
####################################################################
class ExtrasItem(BaseExtrasItem):
    def __init__( self, directory, filename, isFileMatchExtra=False, extrasDb=None ):
        self.extrasDb = extrasDb
        self.watched = 0
        self.totalDuration = -1
        self.resumePoint = 0
        BaseExtrasItem.__init__(self, directory, filename, isFileMatchExtra)
        self._loadState()

    # Note: An attempt was made to re-use the existing XBMC database to
    # read the playcount to work out if a video file has been watched,
    # however this did not seem to work, call was:
    # json_query = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Files.GetFileDetails", "params": {"file": "%s", "media": "video", "properties": [ "playcount" ]},"id": 1 }' % filename)
    # Even posted on the forum, but this hasn't resolved it:
    # http://forum.xbmc.org/showthread.php?tid=177368
    def getWatched(self):
        return self.watched

    # If the playing progress should be recorded for this file, things like
    # ISO's and VOBs do not handle this well as the incorrect values are
    # returned from the player
    def shouldStoreProgress(self):
        if self.getVOBFile() != None:
            return False
        # Get the extension of the file
        fileExt = os.path.splitext( self.getFilename() )[1]
        if (fileExt == None) or (fileExt == "") or (fileExt.lower() == '.iso') :
            return False
        # Default is true
        return True


    def setTotalDuration(self, totalDuration):
        # Do not set the total duration on DVD Images as
        # this will be incorrect
        if not self.shouldStoreProgress():
            return

        self.totalDuration = totalDuration

    def getTotalDuration(self):
        if self.totalDuration < 0:
            self.totalDuration = self.getDuration()
        return self.totalDuration

    def getDisplayDuration(self):
        return BaseExtrasItem.getDisplayDuration(self, self.totalDuration)

    def setResumePoint(self, currentPoint):
        # Do not set the resume point on DVD Images as
        # this will be incorrect
        if not self.shouldStoreProgress():
            return

        # Now set the flag to show if it has been watched
        # Consider watched if within 15 seconds of the end
        if (currentPoint + 15 > self.totalDuration) and (self.totalDuration > 0):
            self.watched = 1
            self.resumePoint = 0
        # Consider not watched if not watched at least 5 seconds
        elif currentPoint < 6:
            self.watched = 0
            self.resumePoint = 0
        # Otherwise save the resume point
        else:
            self.watched = 0
            self.resumePoint = currentPoint

    def getResumePoint(self):
        return self.resumePoint

    # Get the string display version of the Resume time
    def getDisplayResumePoint(self):
        # Split the time up ready for display
        minutes, seconds = divmod(self.resumePoint, 60)

        hoursString = ""        
        if minutes > 60:
            # Need to collect hours if needed
            hours, minutes = divmod(minutes, 60)
            hoursString = "%02d:" % hours
        
        newLabel = "%s%02d:%02d" % (hoursString, minutes, seconds)
        return newLabel


    def isResumable(self):
        if self.watched == 1 or self.resumePoint < 1:
            return False
        return True

    def saveState(self):
        # Do not save the state on DVD Images as
        # this will be incorrect
        if not self.shouldStoreProgress():
            return

        if self.extrasDb == None:
            log("ExtrasItem: Database not enabled")
            return
        
        log("ExtrasItem: Saving state for %s" % self.getFilename())

        rowId = -1
        # There are some cases where we want to remove the entries from the database
        # This is the case where the resume point is 0, watched is 0
        if (self.resumePoint == 0) and (self.watched == 0):
            self.extrasDb.delete(self.getFilename())
        else:
            rowId = self.extrasDb.insertOrUpdate(self.getFilename(), self.resumePoint, self.totalDuration, self.getWatched())
        return rowId

    def _loadState(self):
        if self.extrasDb == None:
            log("ExtrasItem: Database not enabled")
            return

        log("ExtrasItem: Loading state for %s" % self.getFilename())

        returnData = self.extrasDb.select(self.getFilename())

        if returnData != None:
            self.resumePoint = returnData['resumePoint']
            self.totalDuration = returnData['totalDuration']
            self.watched = returnData['watched']


###################################
# Custom Player to play the extras
###################################
class ExtrasPlayer(xbmc.Player):
    def __init__(self, *args):
        self.completed = False
        xbmc.Player.__init__(self, *args)

    # Play the given Extras File
    def play(self, extrasItem):
        play = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        listitem = self._getListItem(extrasItem)
        play.clear()
        play.add(extrasItem.getMediaFilename(), listitem)
        xbmc.Player.play(self, play)

    # Play a list of extras
    def playAll(self, extrasItems):
        play = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        play.clear()

        for exItem in extrasItems:
            listitem = self._getListItem(exItem)
            play.add(exItem.getMediaFilename(), listitem)

        xbmc.Player.play(self, play)

    # Create a list item from an extras item
    def _getListItem(self, extrasItem):
        listitem = xbmcgui.ListItem()
        # Set the display title on the video play overlay
        listitem.setInfo('video', {'studio': __addon__.getLocalizedString(32001) + " - " + SourceDetails.getTitle()})
        listitem.setInfo('video', {'Title': extrasItem.getDisplayName()})
        
        # If both the Icon and Thumbnail is set, the list screen will choose to show
        # the thumbnail
        if extrasItem.getIconImage() != "":
            listitem.setIconImage(extrasItem.getIconImage())
        if extrasItem.getThumbnailImage() != "":
            listitem.setThumbnailImage(extrasItem.getThumbnailImage())
        
        # Record if the video should start playing part-way through
        if extrasItem.isResumable():
            if extrasItem.getResumePoint() > 1:
                listitem.setProperty('StartOffset', str(extrasItem.getResumePoint()))
        return listitem

####################################################
# Class to control displaying and playing the extras
####################################################
class VideoExtrasDialog(xbmcgui.Window):
    def showList(self, exList):
        # Get the list of display names
        displayNameList = []
        for anExtra in exList:
            log("VideoExtrasDialog: filename: %s" % anExtra.getFilename())
            displayNameList.append(anExtra.getDisplayName())

        addPlayAll = (len(exList) > 1)
        if addPlayAll:
            # Play All Selection Option
            displayNameList.insert(0, __addon__.getLocalizedString(32101) )

        # Show the list to the user
        select = xbmcgui.Dialog().select(__addon__.getLocalizedString(32001), displayNameList)

        # User has made a selection, -1 is exit
        if select != -1:
            xbmc.executebuiltin("Dialog.Close(all, true)", True)
            extrasPlayer = ExtrasPlayer()
            waitLoop = 0
            while extrasPlayer.isPlaying() and waitLoop < 10:
                xbmc.sleep(100)
                waitLoop = waitLoop + 1
            extrasPlayer.stop()
            # Give anything that was already playing time to stop
            while extrasPlayer.isPlaying():
                xbmc.sleep(100)
            if select == 0 and addPlayAll == True:
                playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
                playlist.clear()
                extrasPlayer.playAll( exList )
            else:
                itemToPlay = select
                # If we added the PlayAll option to the list need to allow for it
                # in the selection, so add one
                if addPlayAll == True:
                    itemToPlay = itemToPlay - 1
                log( "VideoExtrasDialog: Start playing %s" % exList[itemToPlay].getFilename() )
                extrasPlayer.play( exList[itemToPlay] )
            while extrasPlayer.isPlayingVideo():
                xbmc.sleep(100)
        else:
            return False
        return True


################################################
# Class to control Searching for the extra files
################################################
class VideoExtrasFinder():
    def __init__(self, extrasDb=None):
        self.extrasDb = extrasDb
        
    # Controls the loading of the information for Extras Files
    def loadExtras(self, path, filename, exitOnFirst=False):
        # Check if the files are stored in a custom path
        if Settings.isCustomPathEnabled():
            filename = None
            path = self._getCustomPathDir(path)
            
            if path == None:
                return []
            else:
                log("VideoExtrasFinder: Searching in custom path %s" % path)
        return self.findExtras(path, filename, exitOnFirst)

    # Calculates and checks the path that files should be in
    # if using a custom path
    def _getCustomPathDir(self, path):
        # Work out which section to look in
        typeSection = Settings.getCustomPathMoviesDir()
        if not xbmc.getCondVisibility("Container.Content(movies)"):
            typeSection = Settings.getCustomPathTvShowsDir()

        # Get the last element of the path
        pathLastDir = os.path.split(path)[1]

        # Create the path with this added
        custPath = os_path_join(Settings.getCustomPath(), typeSection)
        custPath = os_path_join(custPath, pathLastDir)
        log("VideoExtrasFinder: Checking existence of custom path %s" % custPath)

        # Check if this path exists
        if not xbmcvfs.exists(custPath):
            # If it doesn't exist, check the path before that, this covers the
            # case where there is a TV Show with each season in it's own directory
            path2ndLastDir = os.path.split((os.path.split(path)[0]))[1]
            custPath = os_path_join(Settings.getCustomPath(), typeSection)
            custPath = os_path_join(custPath, path2ndLastDir)
            custPath = os_path_join(custPath, pathLastDir)
            log("VideoExtrasFinder: Checking existence of custom path %s" % custPath)
            if not xbmcvfs.exists(custPath):
                # If it still does not exist then check just the 2nd to last path
                custPath = os_path_join(Settings.getCustomPath(), typeSection)
                custPath = os_path_join(custPath, path2ndLastDir)
                log("VideoExtrasFinder: Checking existence of custom path %s" % custPath)
                if not xbmcvfs.exists(custPath):
                    custPath = None

        return custPath
        
    
    # Searches a given path for extras files
    def findExtras(self, path, filename, exitOnFirst=False):
        # Get the extras that are stored in the extras directory i.e. /Extras/
        files = self._getExtrasDirFiles(path, exitOnFirst)
        
        # Check if we only want the first entry, in which case exit after
        # we find the first
        if files and (exitOnFirst == True):
            return files
        
        # Then add the files that have the extras tag in the name i.e. -extras-
        files.extend( self._getExtrasFiles( path, filename, exitOnFirst ) )

        # Check if we only want the first entry, in which case exit after
        # we find the first
        if files and (exitOnFirst == True):
            return files
        
        if Settings.isSearchNested():
            files.extend( self._getNestedExtrasFiles( path, filename, exitOnFirst ) )
        files.sort()
        
        # Check if we have found any extras at this point
        if not files:
            # Check if we have a DVD image directory or Bluray image directory
            if (os.path.split(path)[1] == 'VIDEO_TS') or (os.path.split(path)[1] == 'BDMV'):
                log("VideoExtrasFinder: DVD image directory detected, checking = %s" % os.path.split(path)[0])
                files = self.findExtras(os.path.split(path)[0], filename, exitOnFirst)
        return files

    # Gets any extras files that are in the given extras directory
    def _getExtrasDirFiles(self, basepath, exitOnFirst=False):
        # If a custom path, then don't looks for the Extras directory
        if not Settings.isCustomPathEnabled():
            # Add the name of the extras directory to the end of the path
            extrasDir = os_path_join( basepath, Settings.getExtrasDirName() )
        else:
            extrasDir = basepath
        log( "VideoExtrasFinder: Checking existence for %s" % extrasDir )
        extras = []
        # Check if the extras directory exists
        if xbmcvfs.exists( extrasDir ):
            # lest everything in the extras directory
            dirs, files = xbmcvfs.listdir( extrasDir )
            for filename in files:
                log( "VideoExtrasFinder: found file: %s" % filename)
                # Check each file in the directory to see if it should be skipped
                if not self._shouldSkipFile(filename):
                    extrasFile = os_path_join( extrasDir, filename )
                    extraItem = ExtrasItem(extrasDir, extrasFile, extrasDb=self.extrasDb)
                    extras.append(extraItem)
                    # Check if we are only looking for the first entry
                    if exitOnFirst == True:
                        break
            # Now check all the directories in the "Extras" directory
            # Need to see if they contain a DVD image
            for dirName in dirs:
                log( "VideoExtrasFinder: found directory: %s" % dirName)
                # Check each directory to see if it should be skipped
                if not self._shouldSkipFile(dirName):
                    extrasSubDir = os_path_join( extrasDir, dirName )
                    # Check to see if this sub-directory is a DVD directory by checking
                    # to see if there is VIDEO_TS directory
                    videoTSDir = os_path_join( extrasSubDir, 'VIDEO_TS' )
                    # Also check for Bluray
                    videoBluRayDir = os_path_join( extrasSubDir, 'BDMV' )
                    if xbmcvfs.exists( videoTSDir ) or xbmcvfs.exists( videoBluRayDir ):
                        extraItem = ExtrasItem(extrasDir, extrasSubDir, extrasDb=self.extrasDb)
                        extras.append(extraItem)
                        
                    # Check if we are only looking for the first entry
                    if exitOnFirst == True:
                        break

        return extras

    def _getNestedExtrasFiles(self, basepath, filename, exitOnFirst=False):
        extras = []
        if xbmcvfs.exists( basepath ):
            dirs, files = xbmcvfs.listdir( basepath )
            for dirname in dirs:
                dirpath = os_path_join( basepath, dirname )
                log( "VideoExtrasFinder: Nested check in directory: %s" % dirpath )
                if( dirname != Settings.getExtrasDirName() ):
                    log( "VideoExtrasFinder: Check directory: %s" % dirpath )
                    extras.extend( self._getExtrasDirFiles(dirpath, exitOnFirst) )
                     # Check if we are only looking for the first entry
                    if files and (exitOnFirst == True):
                        break
                    extras.extend( self._getExtrasFiles( dirpath, filename, exitOnFirst ) )
                     # Check if we are only looking for the first entry
                    if files and (exitOnFirst == True):
                        break
                    extras.extend( self._getNestedExtrasFiles( dirpath, filename, exitOnFirst ) )
                     # Check if we are only looking for the first entry
                    if files and (exitOnFirst == True):
                        break
        return extras

    # Search for files with the same name as the original video file
    # but with the extras tag on, this will not recurse directories
    # as they must exist in the same directory
    def _getExtrasFiles(self, filepath, filename, exitOnFirst=False):
        extras = []
        extrasTag = Settings.getExtrasFileTag()

        # If there was no filename given, nothing to do
        if (filename == None) or (filename == "") or (extrasTag == ""):
            return extras
        directory = filepath
        dirs, files = xbmcvfs.listdir(directory)

        for aFile in files:
            if not self._shouldSkipFile(aFile) and (extrasTag in aFile) and aFile.startswith(os.path.splitext(filename)[0] + extrasTag):
                extrasFile = os_path_join( directory, aFile )
                extraItem = ExtrasItem(directory, extrasFile, True, extrasDb=self.extrasDb)
                extras.append(extraItem)
                # Check if we are only looking for the first entry
                if exitOnFirst == True:
                    break
        return extras

    # Checks if a file should be skipped because it is in the exclude list
    def _shouldSkipFile(self, filename):
        shouldSkip = False
        if( Settings.getExcludeFiles() != "" ):
            m = re.search(Settings.getExcludeFiles(), filename )
        else:
            m = ""
        if m:
            shouldSkip = True
            log( "VideoExtrasFinder: Skipping file: %s" % filename)
        return shouldSkip


#################################
# Main Class to control the work
#################################
class VideoExtras():
    def __init__( self, inputArg ):
        log( "VideoExtras: Finding extras for %s" % inputArg )
        self.baseDirectory = inputArg
        if self.baseDirectory.startswith("stack://"):
            self.baseDirectory = self.baseDirectory.split(" , ")[0]
            self.baseDirectory = self.baseDirectory.replace("stack://", "")
        # There is a problem if some-one is using windows shares with
        # \\SERVER\Name as when the addon gets called the first \ gets
        # removed, making an invalid path, so we add it back here
        elif self.baseDirectory.startswith("\\"):
            self.baseDirectory = "\\" + self.baseDirectory

        # Support special paths like smb:// means that we can not just call
        # os.path.isfile as it will return false even if it is a file
        # (A bit of a shame - but that's the way it is)
        fileExt = os.path.splitext( self.baseDirectory )[1]
        # If this is a file, then get it's parent directory
        if fileExt != None and fileExt != "":
            self.baseDirectory = os.path.dirname(self.baseDirectory)
            self.filename = (os.path.split(inputArg))[1]
        else:
            self.filename = None
        log( "VideoExtras: Root directory: %s" % self.baseDirectory )

    def findExtras(self, exitOnFirst=False, extrasDb=None):
        # Display the busy icon while searching for files
        xbmc.executebuiltin( "ActivateWindow(busydialog)" )
        files = []
        try:
            extrasFinder = VideoExtrasFinder(extrasDb)
            files = extrasFinder.loadExtras(self.baseDirectory, self.filename, exitOnFirst )
        except:
            log("VideoExtras: %s" % traceback.format_exc())
        xbmc.executebuiltin( "Dialog.Close(busydialog)" )
        return files

    # Enable and disable the display of the extras button
    def checkButtonEnabled(self):
        # See if the option to force the extras button is enabled,
        # if which case just make sure the hide option is cleared
        if Settings.isForceButtonDisplay():
            xbmcgui.Window( 12003 ).clearProperty("HideVideoExtrasButton")
            log("VideoExtras: Force VideoExtras Button Enabled")
        else:
            # Search for the extras, stopping when the first is found
            # only want to find out if the button should be available
            files = self.findExtras(True)
            if files:
                # Set a flag on the window so we know there is data
                xbmcgui.Window( 12003 ).clearProperty("HideVideoExtrasButton")
                log("VideoExtras: Button Enabled")
            else:
                # Hide the extras button, there are no extras
                xbmcgui.Window( 12003 ).setProperty( "HideVideoExtrasButton", "true" )
                log("VideoExtras: Button disabled")

    # Checks if the selected value has extras, setting a custom flag
    def hasExtras(self, flag):
        # Get the current window or dialog
        try: windowid = xbmcgui.getCurrentWindowDialogId()
        except: windowid = 9999
        if windowid == 9999:
            windowid = xbmcgui.getCurrentWindowId()

        # Search for the extras, stopping when the first is found
        # only want to find out if the button should be available
        files = self.findExtras(True)
        if files:
            # Set a flag on the window so we know there is data
            xbmcgui.Window( windowid ).setProperty(flag, "true")
            log("VideoExtras: Has Extras")
        else:
            # Clear the flag, there are no extras
            xbmcgui.Window( windowid ).clearProperties(flag)
            log("VideoExtras: Does Not Have Extras")


    def run(self, files):
        # All the files have been retrieved, now need to display them       
        if not files:
            # "Info", "No extras found"
            xbmcgui.Dialog().ok(__addon__.getLocalizedString(32102), __addon__.getLocalizedString(32103))
        else:
            isTvTunesAlreadySet = True
            needsWindowReset = True
            
            # Make sure we don't leave global variables set
            try:
                # Check which listing format to use
                if Settings.isDetailedListScreen():
                    # Check if TV Tunes override is already set
                    isTvTunesAlreadySet = (xbmcgui.Window( 12000 ).getProperty("TvTunesContinuePlaying").lower() == "true")
                    # If TV Tunes is running we want to ensure that we still keep the theme going
                    # so set this variable on the home screen
                    if not isTvTunesAlreadySet:
                        log("VideoExtras: Setting TV Tunes override")
                        xbmcgui.Window( 12000 ).setProperty( "TvTunesContinuePlaying", "True" )
                    else:
                        log("VideoExtras: TV Tunes override already set")
    
                    extrasWindow = VideoExtrasWindow.createVideoExtrasWindow(files=files)
                    xbmc.executebuiltin( "Dialog.Close(movieinformation)", True )
                    extrasWindow.doModal()
                else:
                    extrasWindow = VideoExtrasDialog()
                    needsWindowReset = extrasWindow.showList( files )
                
                # The video selection will be the default return location
                if (not Settings.isMenuReturnVideoSelection()) and needsWindowReset:
                    if Settings.isMenuReturnHome():
                        xbmc.executebuiltin("xbmc.ActivateWindow(home)", True)
                    else:
                        infoDialogId = 12003
                        # Put the information dialog back up
                        xbmc.executebuiltin("xbmc.ActivateWindow(movieinformation)")
                        if Settings.isMenuReturnExtras():
                            # Wait for the Info window to open, it can take a while
                            # this is to avoid the case where the exList dialog displays
                            # behind the info dialog
                            counter = 0
                            while( xbmcgui.getCurrentWindowDialogId() != infoDialogId) and (counter <30):
                                xbmc.sleep(100)
                                counter = counter + 1
                            # Allow time for the screen to load - this could result in an
                            # action such as starting TvTunes
                            xbmc.sleep(1000)
                            # Before showing the list, check if someone has quickly
                            # closed the info screen while it was opening and we were waiting
                            if xbmcgui.getCurrentWindowDialogId() == infoDialogId:
                                # Reshow the exList that was previously generated
                                self.run(files)
            except:
                log("ExtrasItem: %s" % traceback.format_exc())

            # Tidy up the TV Tunes flag if we set it
            if not isTvTunesAlreadySet:
                log("VideoExtras: Clearing TV Tunes override")
                xbmcgui.Window( 12000 ).clearProperty( "TvTunesContinuePlaying" )


#####################################################################
# Extras display Window that contains a few more details and looks
# more like the TV SHows listing
#####################################################################
class VideoExtrasWindow(xbmcgui.WindowXML):
    def __init__( self, *args, **kwargs ):
        # Copy off the key-word arguments
        # The non keyword arguments will be the ones passed to the main WindowXML
        self.files = kwargs.pop('files')
        self.lastRecordedListPosition = -1

    # Static method to create the Window class
    @staticmethod
    def createVideoExtrasWindow(files):
#        return VideoExtrasWindow("MyVideoNav.xml", os.getcwd(), files=files, src=src)
        return VideoExtrasWindow("script-videoextras-main.xml", __addon__.getAddonInfo('path').decode("utf-8"), files=files)

    def onInit(self):
        # Need to clear the list of the default items
        self.clearList()
        
        for anExtra in self.files:
            log("VideoExtrasWindow: filename: %s" % anExtra.getFilename())

            # Label2 is used to store the duration in HH:MM:SS format
            anItem = xbmcgui.ListItem(anExtra.getDisplayName(), anExtra.getDisplayDuration(), path=SourceDetails.getFilenameAndPath())
            anItem.setProperty("FileName", anExtra.getFilename())
            anItem.setInfo('video', { 'PlayCount': anExtra.getWatched() })
            anItem.setInfo('video', { 'Title': SourceDetails.getTitle() })
            # We store the duration here, but it is only in minutes and does not
            # look very good if displayed, so we also set Label2 to a viewable value
            intDuration = anExtra.getDuration()
            # Only add the duration if there is one
            if intDuration > 0:
                anItem.setInfo('video', { 'Duration': int(anExtra.getDuration()/60) })
            if SourceDetails.getTvShowTitle() != "":
                anItem.setInfo('video', { 'TvShowTitle': SourceDetails.getTvShowTitle() })

            # If both the Icon and Thumbnail is set, the list screen will choose to show
            # the thumbnail
            if anExtra.getIconImage() != "":
                anItem.setIconImage(anExtra.getIconImage())
            if anExtra.getThumbnailImage() != "":
                anItem.setThumbnailImage(anExtra.getThumbnailImage())

            # The following two will give us the resume flag
            anItem.setProperty("TotalTime", str(anExtra.getTotalDuration()))
            anItem.setProperty("ResumeTime", str(anExtra.getResumePoint()))

            # Set the background image
            anItem.setProperty( "Fanart_Image", anExtra.getFanArt() )

            self.addItem(anItem)
        
        # Before we return, set back the selected on screen item to the one just watched
        # This is in the case of a reload
        if self.lastRecordedListPosition > 0:
            self.setCurrentListPosition(self.lastRecordedListPosition)
        
        xbmcgui.WindowXML.onInit(self)

    # Handle the close action and the context menu request
    def onAction(self, action):
        # actioncodes from https://github.com/xbmc/xbmc/blob/master/xbmc/guilib/Key.h
        ACTION_PREVIOUS_MENU = 10
        ACTION_NAV_BACK      = 92
        ACTION_CONTEXT_MENU = 117

        if (action == ACTION_PREVIOUS_MENU) or (action == ACTION_NAV_BACK):
            log("VideoExtrasWindow: Close Action received: %s" % str(action))
            self.close()
        elif action == ACTION_CONTEXT_MENU:
            # Get the item that was clicked on
            extraItem = self._getCurrentSelection()
            # create the context window
            contextWindow = VideoExtrasContextMenu.createVideoExtrasContextMenu(extraItem)
            contextWindow.doModal()
            
            # Check the return value, if exit, then we play nothing
            if contextWindow.isExit():
                return
            # If requested to restart from beginning, reset the resume point before playing
            if contextWindow.isRestart():
                extraItem.setResumePoint(0)
                self._performPlayAction(extraItem)
                
            if contextWindow.isResume():
                self._performPlayAction(extraItem)

            if contextWindow.isMarkUnwatched():
                # Need to remove the row from the database
                if Settings.isDatabaseEnabled():
                    # Refresh the screen now that we have change the flag
                    extraItem.setResumePoint(0)
                    extraItem.saveState()
                    self.onInit()

            if contextWindow.isMarkWatched():
                # If marking as watched we need to set the resume time so it doesn't
                # start in the middle the next time it starts
                if Settings.isDatabaseEnabled():
                    extraItem.setResumePoint(extraItem.getTotalDuration())
                    extraItem.saveState()
                    self.onInit()

            if contextWindow.isEditTitle():
                # Prompt the user for the new name
                keyboard = xbmc.Keyboard()
                keyboard.setDefault(extraItem.getDisplayName())
                keyboard.doModal()
                
                if keyboard.isConfirmed():
                    try:
                        newtitle = keyboard.getText().decode("utf-8")
                    except:
                        newtitle = keyboard.getText()
                        
                    # Only set the title if it has changed
                    if (newtitle != extraItem.getDisplayName()) and (len(newtitle) > 0):
                        result = extraItem.setTitle(newtitle)
                        if not result:
                            xbmcgui.Dialog().ok(__addon__.getLocalizedString(32102), __addon__.getLocalizedString(32109))
                        else:
                            self.onInit()


    def onClick(self, control):
        WINDOW_LIST_ID = 51
        # Check to make sure that this click was for the extras list
        if control != WINDOW_LIST_ID:
            return
        
        # Get the item that was clicked on
        extraItem = self._getCurrentSelection()
        
        if extraItem == None:
            # Something has gone very wrong, there is no longer the item that was selected
            log("VideoExtrasWindow: Unable to match item to current selection")
            return
        
        # If part way viewed prompt the user for resume or play from beginning
        if extraItem.getResumePoint() > 0:
            resumeWindow = VideoExtrasResumeWindow.createVideoExtrasResumeWindow(extraItem.getDisplayResumePoint())
            resumeWindow.doModal()
            
            # Check the return value, if exit, then we play nothing
            if resumeWindow.isExit():
                return
            # If requested to restart from beginning, reset the resume point before playing
            if resumeWindow.isRestart():
                extraItem.setResumePoint(0)
            # Default is to actually resume
            
        self._performPlayAction(extraItem)
        

    # Calls the media player to play the selected item
    def _performPlayAction(self, extraItem):
        extrasPlayer = ExtrasPlayer()
        extrasPlayer.play( extraItem )
        
        while not extrasPlayer.isPlayingVideo():
            xbmc.sleep(1)
        
        # Get the total duration and round it down to the nearest second
        videoDuration = int(extrasPlayer.getTotalTime())
        log("VideoExtrasWindow: TotalTime of video = %d" % videoDuration)
        extraItem.setTotalDuration(videoDuration)

        currentTime = 0
        # Wait for the player to stop
        while extrasPlayer.isPlayingVideo():
            # Keep track of where the current video is up to
            currentTime = int(extrasPlayer.getTime())
            xbmc.sleep(100)

        # Record the time that the player actually stopped
        log("VideoExtrasWindow: Played to time = %d" % currentTime)
        extraItem.setResumePoint(currentTime)
        
        # Now update the database with the fact this has now been watched
        extraItem.saveState()

    # Search the list of extras for a given filename
    def _getCurrentSelection(self):
        self.lastRecordedListPosition = self.getCurrentListPosition()
        log("VideoExtrasWindow: List position = %d" % self.lastRecordedListPosition)
        anItem = self.getListItem(self.lastRecordedListPosition)
        filename = anItem.getProperty("Filename")
        log("VideoExtrasWindow: Selected file = %s" % filename)
        # Now search the Extras list for a match
        for anExtra in self.files:
            if anExtra.isFilenameMatch( filename ):
                log("VideoExtrasWindow: Found  = %s" % filename)
                return anExtra
        return None



##################################################
# Dialog window to find out is a video should be
# resumes or started from the beginning
##################################################
class VideoExtrasResumeWindow(xbmcgui.WindowXMLDialog):
    EXIT = 1
    RESUME = 2
    RESTART = 40

    def __init__( self, *args, **kwargs ):
        # Copy off the key-word arguments
        # The non keyword arguments will be the ones passed to the main WindowXML
        self.resumetime = kwargs.pop('resumetime')
        self.selectionMade = VideoExtrasResumeWindow.EXIT

    # Static method to create the Window Dialog class
    @staticmethod
    def createVideoExtrasResumeWindow(resumetime=0):
        return VideoExtrasResumeWindow("script-videoextras-resume.xml", __addon__.getAddonInfo('path').decode("utf-8"), resumetime=resumetime)

    def onInit(self):
        # Need to populate the resume point
        resumeButton = self.getControl(VideoExtrasResumeWindow.RESUME)
        currentLabel = resumeButton.getLabel()
        newLabel = "%s %s" % (currentLabel, self.resumetime)

        # Reset the resume label with the addition of the time
        resumeButton.setLabel(newLabel)
        xbmcgui.WindowXMLDialog.onInit(self)

    def onClick(self, control):
        # Save the item that was clicked
        # Item ID 2 is resume
        # Item ID 40 is start from beginning
        self.selectionMade = control
        # If not resume or restart - we just want to exit without playing
        if not (self.isResume() or self.isRestart()):
            self.selectionMade = VideoExtrasResumeWindow.EXIT
        # Close the dialog after the selection
        self.close()

    def isResume(self):
        return self.selectionMade == VideoExtrasResumeWindow.RESUME
    
    def isRestart(self):
        return self.selectionMade == VideoExtrasResumeWindow.RESTART
    
    def isExit(self):
        return self.selectionMade == VideoExtrasResumeWindow.EXIT
       

#######################################################
# Context Menu
#
# - Resume From 00:00
# - Play From Start
# - Mark as watched (If not watched)
# - Mark as unwatched (If watched)
# - Set title (Write NFO file if directory writable)
#######################################################
class VideoExtrasContextMenu(xbmcgui.WindowXMLDialog):
    EXIT = 1
    RESUME = 2
    RESTART = 40
    MARK_WATCHED = 41
    MARK_UNWATCHED = 42
    EDIT_TITLE = 43
    
    def __init__( self, *args, **kwargs ):
        # Copy off the key-word arguments
        # The non keyword arguments will be the ones passed to the main WindowXML
        self.extraItem = kwargs.pop('extraItem')
        self.selectionMade = VideoExtrasContextMenu.EXIT

    # Static method to create the Window Dialog class
    @staticmethod
    def createVideoExtrasContextMenu(extraItem):
        # Pull out the resume time as this will be processed by the base class
        return VideoExtrasContextMenu("script-videoextras-context.xml", __addon__.getAddonInfo('path').decode("utf-8"), extraItem=extraItem)

    def onInit(self):
        # Need to populate the resume point
        resumeButton = self.getControl(VideoExtrasContextMenu.RESUME)
        currentLabel = resumeButton.getLabel()
        newLabel = "%s %s" % (currentLabel, self.extraItem.getDisplayResumePoint())

        # Reset the resume label with the addition of the time
        resumeButton.setLabel(newLabel)

        xbmcgui.WindowXMLDialog.onInit(self)

    def onClick(self, control):
        # Save the item that was clicked
        self.selectionMade = control
        # If not resume or restart - we just want to exit without playing
        if not (self.isResume() or self.isRestart() or self.isMarkWatched() or self.isMarkUnwatched() or self.isEditTitle()):
            self.selectionMade = VideoExtrasContextMenu.EXIT
        # Close the dialog after the selection
        self.close()

    def isResume(self):
        return self.selectionMade == VideoExtrasContextMenu.RESUME
    
    def isRestart(self):
        return self.selectionMade == VideoExtrasContextMenu.RESTART
    
    def isExit(self):
        return self.selectionMade == VideoExtrasContextMenu.EXIT

    def isMarkWatched(self):
        return self.selectionMade == VideoExtrasContextMenu.MARK_WATCHED

    def isMarkUnwatched(self):
        return self.selectionMade == VideoExtrasContextMenu.MARK_UNWATCHED

    def isEditTitle(self):
        return self.selectionMade == VideoExtrasContextMenu.EDIT_TITLE


##################################################
# Class to store the details of the selected item
##################################################
class SourceDetails():
    title = None
    tvshowtitle = None
    fanart = None
    filenameAndPath = None

    # Forces the loading of all the source details
    # This is needed if the "Current Window" is going to
    # change - and we need a reference to the source before
    # it changes
    @staticmethod
    def forceLoadDetails():
        SourceDetails.getFanArt()
        SourceDetails.getFilenameAndPath()
        SourceDetails.getTitle()
        SourceDetails.getTvShowTitle()

    @staticmethod
    def getTitle():
        if SourceDetails.title == None:
            # Get the title of the Movie or TV Show
            if WindowShowing.isTv():
                SourceDetails.title = xbmc.getInfoLabel( "ListItem.TVShowTitle" )
            else:
                SourceDetails.title = xbmc.getInfoLabel( "ListItem.Title" )
            # There are times when the title has a different encoding
            try:
                SourceDetails.title = SourceDetails.title.decode("utf-8")
            except:
                pass

        return SourceDetails.title

    @staticmethod
    def getTvShowTitle():
        if SourceDetails.tvshowtitle == None:
            if WindowShowing.isTv():
                SourceDetails.tvshowtitle = xbmc.getInfoLabel( "ListItem.TVShowTitle" )
            else:
                SourceDetails.tvshowtitle = ""
            # There are times when the title has a different encoding
            try:
                SourceDetails.tvshowtitle = SourceDetails.tvshowtitle.decode("utf-8")
            except:
                pass

        return SourceDetails.tvshowtitle

    # This is a bit of a hack, when we set the path we need to set it an extra
    # directory below where we really are - this path is not used to retrieve
    # the extras files (This class highlights where the script was called from)
    # It is used to trigger the TV Tunes, and for some reason between VideoExtras
    # setting the value and TvTunes getting it, it loses the final directory
    @staticmethod
    def getFilenameAndPath():
        if SourceDetails.filenameAndPath == None:
            SourceDetails.filenameAndPath = xbmc.getInfoLabel( "ListItem.FilenameAndPath" ) + "Extras"
        return SourceDetails.filenameAndPath
    
    @staticmethod
    def getFanArt():
        if SourceDetails.fanart == None:
            # Save the background
            SourceDetails.fanart = xbmc.getInfoLabel( "ListItem.Property(Fanart_Image)" )
        return SourceDetails.fanart


#########################
# Main
#########################
try:
    if len(sys.argv) > 1:
        # get the type of operation
        log("Operation = %s" % sys.argv[1])

        # Load the details of the current source of the extras        
        SourceDetails.forceLoadDetails()
        
        # Should the existing database be removed
        if sys.argv[1] == "cleanDatabase":
            extrasDb = ExtrasDB()
            extrasDb.cleanDatabase()
        
        # Check for a request to check for extras
        elif len(sys.argv) > 3 and sys.argv[1] == "hasExtras":
            
            if not ("plugin://" in sys.argv[3]):
                videoExtras = VideoExtras(sys.argv[3])
                videoExtras.hasExtras(sys.argv[2])
            
        # All other operations require at least 2 arguments
        elif len(sys.argv) > 2:
            # Make sure we are not passed a plugin path
            if "plugin://" in sys.argv[2]:
                if sys.argv[1] == "check":
                    xbmcgui.Window( 12003 ).setProperty( "HideVideoExtrasButton", "true" )
            else:
                # Create the extras class that deals with any extras request
                videoExtras = VideoExtras(sys.argv[2])
        
                # We are either running the command or just checking for existence
                if sys.argv[1] == "check":
                    videoExtras.checkButtonEnabled()
                else:
                    # Check if the use database setting is enabled
                    extrasDb = None
                    if Settings.isDatabaseEnabled():
                        extrasDb = ExtrasDB()
                        # Make sure the database has been created
                        extrasDb.createDatabase()
                    # Perform the search command
                    files = videoExtras.findExtras(extrasDb=extrasDb)
                    # need to display the extras
                    videoExtras.run(files)
except:
    log("ExtrasItem: %s" % traceback.format_exc())
