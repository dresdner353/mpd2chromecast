## mpd2chromecast

This is a python script and related shell wrapper that you can deploy on a Volumio or moOde installation and use it to integrate single and multi-room playback with Google Chromecast devices and all variants such as Google/Nest Home speakers.

The script uses an python-mpd2 (https://github.com/Mic92/python-mpd2) to monitor playback state of MPD, the underlying media player layer used by both Volumio and moOde. It then generates and sends a URL for the playing file to the target chromecast device or group. The chromecast then streams the file contents and plays the file. The script uses pychromecast (https://github.com/balloob/pychromecast) for the Google Cast integration. 

As you invoke play, stop, pause, next/previous and seek actions on your media platform, these are detected by the MPD interface and then relayed to the Chromecast to match the behaviour. The script also provides album artwork support that will appear on screen for video-based chromecasts.

## Installation
For installation on Volumio, [see moOde README](./volumio.md)  
For installation on moOde, [see moOde README](./moOde.md)  

## Selecting Desired Chromecast
After everything is installed and ready to ry out, the first step is to select the desired chromecast or cast-enabled device on your network.

You should first run the set_chromecast.py script to perform a scan and then select the desired device/group. 

For example:
```
$ ./volumio2chromecast/set_chromecast.py --discover
Discovering Chromecasts.. (this may take a while)
Found 11 devices
 0   off
 1   Living Room
 2   Downstairs
 3   Kitchen
 4   Master Bedroom Wifi
 5   Living Room Google Home
 6   Entire House
 7   All Google Homes
 8   Office Google Home
 9   Office Test
10   Hall Google Home
11   Kitchen Google Home
Enter device number: 9
Setting desired Chromecast to [Office Test]
```
This then saves the selected chromecast name in ~/.castrc. 

You can also invoke that script with the --name option to directly set the desired Chromecast without having to scan:
```
$ ./volumio2chromecast/set_chromecast.py --name 'Office'
Setting desired Chromecast to [Office]
```

Lastly, you can also invoke the script without the --discover option and it will simply re-list the last scanned list of devices rather than perform a new discovery. This makes for a faster selection and re-selection of the desired cast device.

## Test Run
To get the script running on a terminal, just do the following:
```
LC_ALL=en_US.UTF-8 ~/volumio2chromecast/mpd2chromecast.py 
```
In this mode, the script will output data every second showing playback status for your media player and any related activity from the Chromecast. Once you have the script running, it should start trying to cast the current playlist to the selected chromecast. Try changing tracks, pausing, skipping and changing volume and you should see the Chromecast react pretty quickly.

Note: The use of LC_ALL set to US UTF-8 was something I was forced to do because when left on my default locale (Ireland UTF-8), something went wrong with how UTF-8 characters we being matched between filenames on the disk and the URLs. I suspect it relates to locale specifics not present within the Raspian image. Forcing US UTF-8 sorts this however.

## Starting the Agent in the Background

To start the agent in the background, use this command:
```
./volumio2chromecast/mpd2chromecast.sh
```
You can also force a restart of the agent using the "restart" option:
```
./volumio2chromecast/mpd2chromecast.sh restart
```

## Enabling the script to run at startup
The shell script mentioned above is crontab friendly in that it can be invoked continually and will only start the agent if it's not found to be running. 

To setup crontab on the Pi:
```
sudo apt-get install cron
sudo update-rc.d cron enable 2 3 4 5
sudo /etc/init.d/cron start
   
crontab -e 
    .. when prompted, select the desired editor and add this line:
    * * * * * /home/volumio/volumio2chromecast/mpd2chromecast.sh > /dev/null

```

## Dynamically switching Chromecast
When using the saved config approach, the script watches the ~/.castrc file for changes. If it detects a change, it reloads config, re-resolves the Chromecast and switches device. It will also try to stop playback on the current device.

All you need to do is run the set_chromecast.py script and specify the new device or select from its menu. Once saved, the playback should switch devices in about 10-20 seconds, giving time for the change to be detected and discovery of the new device to take place.

## Disabling
To stop casting, you can normally either pause playback or clear the playlist. You could also disable the casting permanently by deleting/commenting out the crontab entry. 

However there is an easier way to do this by setting the configured chromecast device to 'off'. 
```
$ ./volumio2chromecast/set_chromecast.py --name 'off'
Setting desired Chromecast to [off]
```
This will cause the script to disconnect from any existing cast device and disable any further attempts to connect to a chromecast until the configured device name is again changed.

## How it works
The script runs four threads:
* MPD/Chromecast  
This is to monitor the playback state of the server via MPD API allowing us to know what is playing and react to track changes, volume, pause/play/skip etc. It then passes these directives to configured chromecast. It also monitors the chromecast status to ensure playback is operational. The native APIs for both Volumio and moOde are also used when performing the cast request but only to obtain the artwork for the current song. That detail is not available via the MPD API.

* Cherrypy (web server)  
This thread provides a simple web server which is used to serve a URL for each track. The chromecasts will use that URL to stream the files for native playback.

* Config  
This thread just monitors config (~/.castrc) and changes one internal global variable for the selected chromecast device.

* Chromecast Discovery  
This thread runs on loop every minute, scanning for available chromecasts and stores the names (in /tmp/castdevices). The intention here is to get platform plugins to leverage that detail for something like a GUI selection of the desired chromecast. The same file is also used for a faster execution of set_chromecast.py (when the --discover option is omitted) instead of having to wait for a scan each time.

## File types that work
MPD will handle a wide range of files natively and work with attached DACs, HDMI or USB interfaces that can handle it. Bear in mind however that we are totally bypassing this layer. We're serving a file URL directly to the Chromecast and all decoding is done by the Chromecast.

### MP3 16/320kbps & FLAC 2.0 16/44
I've had perfect results on all variants of Chromecast (Video, Audio and Home) with standard MP3 320 and FLAC 2.0 16/44. I did not try raw WAV 16/44 but assume it would also work.

### FLAC 2.0 24/96
For 2-channel 24/96 high-res, the normal video Chromecast will play them back but I've noticed it streams into my AVR via HDMI as 48Khz (not certain if that is 16/24 as the AVR does not say). The same 2.0 24/96 seems to stream out of the Chromecast Audio as a SPDIF digital bitstream but will not work with my AVR. It does work with my SMSL headphone amp. So I'm suspecting my Onkyo AVR does not support 24/96 PCM via its SPDIF. But to be clear, I don't know for sure what is coming out from that SPIDF. The headphone amp does not have a display or readout to confirm what it is receiving.

### FLAC 5.1 24/96
The normal video chromecast does not work with these files at all. Playback begins to cast and then abruptly stops. On the Chromecast Audio the playback does work OK with 2-channel analog output. I'm assuming it plays only two channels rather than a mix down. The SPDIF output also worked with my headphone amp but like above I'm not able to confirm what is being output other than my AVR will not play it and my headphone amp will. These files also play via Google Home devices so I'm suspecting there is a common DAC in use on both the Google Home and Chromecast audio devices. 

So I hope you find this useful for you if you are trying to get MPD to play nice with Chromecast. 
