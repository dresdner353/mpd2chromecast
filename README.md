## volumio2chromecast

This is a python script you can deploy on a Volumio installation and use it to control playback via a Google Chromecast device and all variants such as Google/Nest Home speakers.

Note: For installation on moOde, [see moOde README](./moOde.md)  

The script uses the Volumio API to monitor playback state of the app and then passes a URL for the file to the target Chromecast where it will stream the file directly. It uses pychromecast (https://github.com/balloob/pychromecast) for the Chromecast integration. 

As you invoke play, stop, pause, next and previous actions on Volumio's Web IF, these are detected by the script and relayed to the Chromecast to match. 

It's not perfect, but it's an OK start :)

**Note:** This set of steps was orginally working with standard Volumio releases. Alas, Volumio is still based on Raspian Jesse and it's just too old to keep up with working versions of pychromecast, Python3 and other dependencies. So the installation here only really works on beta Volumio images based on Raspian Buster. I had tried all kinds of approaches to recompiling later Python releases on the Jesse stack and just kept hitting one issue after the other. The beta images is by no means perfect and I've seen a few funny behaviours here and there with it. So at this stage, you may need to wait for Volumio devs to get a Buster image available with Volumio if you are expecting more stability.

## Installation

Download the Buster beta image:
https://community.volumio.org/t/volumio-debian-buster-beta-raspi-images-debugging/11988

Usual flash process applies for the install.

After instalation, browse to http://volumio.local/dev and enable the SSH option. Then ssh into the box as volumio@volumio.local, password "volumio" and follow the commands below..

Update package lists and install the related Python3 components:
```
sudo apt-get update
sudo apt-get install python3-pip
sudo pip3 install pychromecast cherrypy
```

Install the script as follows:
```
cd
git clone https://github.com/dresdner353/volumio2chromecast.git
```

## Selecting Desired Chromecast
You should first run the set_chromecast.py script to perform a scan of the available Chromecast devices on your network and then make your selection by number. 

**Note:** The results shown will be for both detected Chromecasts and any cast groups you may have created.. yes multi-room will work here :).

For example:
```
$ ./volumio2chromecast/set_chromecast.py
Discovering Chromecasts.. (this may take a while)
Found 9 devices
 0   Girls Google Home
 1   Cian's Google Home
 2   Living Room
 3   Living Room Google Home
 4   Test Group
 5   Kitchen Google Home
 6   Master Bedroom
 7   Office
 8   Office Google Home
Enter device number: 7
Setting desired Chromecast to [Office]
```
This then saves the selected Chromecast name in ~/.castrc. 

You can also invoke that script with the --name option to directly set the desired Chromecast without having to scan:
```
$ ./volumio2chromecast/set_chromecast.py --name 'Office'
Setting desired Chromecast to [Office]
```

## Test Run
To get the script running on a terminal, just do the following:
```
LC_ALL=en_US.UTF-8  ~/volumio2chromecast/volumio2chromecast.py 
```
In this mode, the script will output data every second showing Volumio playback status and any related activity from the Chromecast. Once you have the script running, it should start trying to cast the current playlist to the selected chromecast. Try changing tracks, pausing, skipping and changing volume and you should see the Chromecast react pretty quickly.

Note: The use of LC_ALL set to US UTF-8 was something I was forced to do because when left on my default locale (Ireland UTF-8), something went wrong with how UTF-8 characters we being matched between filenames on the disk and the URLs. I suspect it relates to locale specifics not present within the Raspian image. Forcing US UTF-8 sorts this however.

## Starting the Agent in the Background

To start the agent in the background, use this command:
```
./volumio2chromecast/volumio2chromecast.sh
```
You can also force a restart of the agent using the "restart" option:
```
./volumio2chromecast/volumio2chromecast.sh restart
```

## Enabling the script to run at startup
The shell script mentioned above is crontab friendly in that it can be invoked continually and will only start the agent if it's not found to be running. 

To setup crontab on the Pi:
```
sudo apt-get install cron
   
crontab -e 
    .. when prompted, select the desired editor and add this line:
    * * * * * /home/volumio/volumio2chromecast/volumio2chromecast.sh > /dev/null

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
* Volumio  
This is to monitor the playback state of the server allowing us to know what is playing and react to track changes, volume, pause/play/skip etc. It then passes these directives to configured chromecast. It also monitors the chromecast status to ensure playback is operational. 

* Cherrypy (web server)  
This thread provides a simple web server which is used to serve a URL for each track. The chromecasts will use that URL to stream the files for native playback.

* Config  
This thread just monitors config (~/.castrc) and changes one internal global variable for the selected chromecast device.

* Chromecast Discovery  
This thread is experimental. It runs on loop every minute, scanning for available chromecasts and stores the names (in /tmp/castdevices). The intention here is to get a Volumio plugin to leverage that detail for something like a GUI selection of the desired chromecast. It's also possible to evolve the set_chromecast.py script to use this file for a faster execution instead of having to wait for a scan each time.


### The Volumio <-> Chromecast Thread in more detail
The Volumio thread checks the Volumio playback state every second and from there, auto casts the playing file URL to the target Chromecast. It responds to play/stop, track and volume changes in real-time. So as you use the Volumio interface to select the desired music, stop/pause/etc it will immediately match the same action via the target Chromecast or cast group. The same thread will use the pychromecast module to obtain a handle object for the configured chromecast. This provides us with the means of monitoring chromecast playback status and also a way to tell it to stop/start and stream a given file. 

Seek will also work if you use Volumio to skip forward or backward within the playing track. The script will force the Chromecast to seek to the same point in the stream. Also during playback every 10 seconds, the Chromecast current elapsed time position is synced back to Volumio if Volumio is at the same elapsed time or even ahead. This is to ensure that Volumio is playing back 1-2 seconds behind the Chromecast. So if you are listening via local Audio output, expect to hear skips every so often as the playback syncs up. But that should not be an issue as the entire point of this integration is to use the Chromecast(s) as the playback devices.

## File types that work
Volumio will handle a wide range of files natively and work with attached DACs, HDMI or USB interfaces that can handle it. Bear in mind however that we are totally bypassing this layer. We're serving a file URL directly to the Chromecast and all decoding is done by the Chromecast.

### MP3 16/320kbps & FLAC 2.0 16/44
I've had perfect results on all variants of Chromecast (Video, Audio and Home) with standard MP3 320 and FLAC 2.0 16/44. I did not try raw WAV 16/44 but assume it would also work.

### FLAC 2.0 24/96
For 2-channel 24/96 high-res, the normal video Chromecast will play them back but I've noticed it streams into my AVR via HDMI as 48Khz (not certain if that is 16/24 as the AVR does not say). The same 2.0 24/96 seems to stream out of the Chromecast Audio as a SPDIF digital bitstream but will not work with my AVR. It does work with my SMSL headphone amp. So I'm suspecting my Onkyo AVR does not support 24/96 PCM via its SPDIF. But to be clear, I don't know for sure what is coming out from that SPIDF. The headphone amp does not have a display or readout to confirm what it is receiving.

### FLAC 5.1 24/96
The normal video chromecast does not work with these files at all. Playback begins to cast and then abruptly stops. On the Chromecast Audio the playback does work OK with 2-channel analog output. I'm assuming it plays only two channels rather than a mix down. The SPDIF output also worked with my headphone amp but like above I'm not able to confirm what is being output other than my AVR will not play it and my headphone amp will. These files also play via Google Home devices so I'm suspecting there is a common DAC in use on both the Google Home and Chromecast audio devices. 

So I hope you find this useful for you if you are trying to get Volumio to play nice with Chromecast. 
