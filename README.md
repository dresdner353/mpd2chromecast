## volumio2chromecast

This is a python script you can deploy on a Volumio installation and use it to control playback via a Google Chromecast device.

The script uses the Volumio API to monitor playback state of the app and then passes a URL for the file to the target Chromecast where it will stream the file directly. It uses pychromecast (https://github.com/balloob/pychromecast) for the Chromecast integration. 

As you invoke play, stop, pause, next and previous actions on Volumio's Web IF, these are detected by the script and relayed to the Chromecast to match. 

It's not perfect, but it's an OK start :)


## Installation

You'll need Python3 running on the Volumio instance and also pull in cherrypy and pychromecast. 

For a Raspberry Pi, you would need to do the following:

sudo nano /etc/apt/sources.list

and add in these two lines:
```
deb http://archive.raspberrypi.org/debian/ jessie main
deb-src http://archive.raspberrypi.org/debian/ jessie main
```

Install the Python3 env and required pip packages:
```
sudo apt-get install python3 python3-setuptools python3-venv python3-dev
sudo easy_install3 pip
```

Copy the script to the RPi volumio home folder and run it as follows:
```
LC_ALL=en_US.UTF-8 ~/volumio2chromecast.py --ip <ip of chromecast> --port <port>

or

LC_ALL=en_US.UTF-8 ~/volumio2chromecast.py --name  <friendly name of chromecast> 
```

I had to use LC_ALL set to en_US.UTF-8 on my environment to get everything to work correctly. Without that change, there were issues with some cast file URLs not matching correctly to the filenames on the drive. 

I have not yet added some supporting scripts to run this in the background yet as it's still very much a work in progress... a prototype realy. In my current test device (Rpi 1B), I'm using the "screen" app to run a background detached terminal which runs the above in a while true loop and I detach from the terminal then when I want to disconnect. I will eventually add a background script that can be tied to cron or whatnot to better manage this or some more appropriate Pi-way of managing a service. I have managed to get the script to run fine for well over a day uninterrupted but it will sometimes get an exception and exit. 

## How it works
When you run the script it will first do a discovery of your specified Chromecast (if you specified it by --name) to obtain its IP and port. That will several seconds. You can alternatively start with the --ip and optional --port options to bypass the discovery stage.

After determining the IP and port of the target chromecast, the script then runs two threads. One thread manages a webserver which is using cherrypy for the engine. That webserver serves up a file tree from / and is used to serve up URLs generated from the currently playing file.

The other thread is a continuous loop using a 1 second sleep that works between the Volumio current play state and the Chromecast playback state. 

At the console, the script will start showing the current Volumio JSON state every second. It gets this by calling the RESTful API function http://localhost:3000/api/v1/getstate

If it detects that something is playing, it will generate a URL for the that file (using the uri field of the volumio state) and invoke a cast of that file URL to the specified Chromecast. That is where the pychromecast module comes in to drive all interaction with the Chromecast. The Chromecast should then call us back on the webserver port to pull its stream URL. It will return at intervals to pull more data of the file as the playback progresses.

By having the regular 1-second status updates from Volumio, it also ties into volume changes, play, pause, next, previous etc. All of these actions at the Volumio interface get relayed to the Chromecast. So as you change track, pause, stop.. Chromecast will follow suit. 

However, there is no seek functionality at this stage. So you can’t skip ahead/back within a given track. 

If the script loses connectivity to the Chromecast it will detect this, re-establish a cast and start streaming again. Even if someone independently casts to the device from another app, this script will steal back control on the next track change. 

To stop the streaming, you clear the queue on Volumio or let the current playlist play out and that will put it into a stopped state on the Volumio end which directs the script to stop casting and release all control over the Chromecast.

I’ve got this to work fine on the normal Google Chromecast, Chromecast Audio and on Google Home devices. I did try to get basic artwork working for the video variant but was struggling with converting the Volumio artwork references it into URLs. 

### Syncing playback and the issue of seek
Just FYI the seek restriction relates to how I had to sync Volumio playback with that of the Chromecast. When you instruct Volumio to play a file, it really is playing the file via the default audio device. The progress of that playback starts as soon as you hit play. But the Chromecast playback is on it’s own timing and subject to how long it takes the Chromecast to receive and react to the streaming request and start streaming the file. 

If both left to their own devices, the Volumio playback is likely to end first. That will cause the script to instruct Chromecast to play the next track before it finished playing the current one. So the approach I took was to force 10-second syncs, where the elapsed time as reported from the Chromecast is used to perform a local seek on Volumio and get it back in sync and likely behind by 1-2 seconds. The cool thing is that once the Chromecast finishes playback, it's idle state is quickly detected and the script invokes the next track via the Volumio API. This syncing only continues each 10 seconds until the track passes 50% progess. At that stage, its safe to leave it alone.

Visually what you see on the Volumio I/F is track time progress as the playback continues and a little niggle every 10 seconds as the sync takes place. So you can’t really listen to the native playback as it will experience drops every 30 seconds with the sync. But in fairness the objective is to listen via the Chromecast.

Also, if during playback, you go and seek further on via Volumio GUI, within 10 seconds it will reset itself back to where the Chromecast progress is. For that reason, we don’t (yet) have a reliable way of having a Volumio seek translate into a seek on the Chromecast. But it is something I’d like to tackle at some point.

## File types that work
Volumio will handle a wide range of files natively and work with attached DACs, HDMI or USB interfaces that can handle it. Bear in mind however that we are totally bypassing this layer. We're serving a file URL directly to the Chromecast and all decoding is done by the Chromecast.

### MP3 16/320kbps & FLAC 2.0 16/44
I've had perfect results on all variants of Chromecast (Video, Audio and Home) with standard MP3 320 and FLAC 2.0 16/44. I did not try raw WAV 16/44 but assume it would also work.

### FLAC 2.0 24/96
For 2-channel 24/96 high-res, the normal video Chromecast will play them back but I've noticed it streams into my AVR via HDMI as 16/48. The same 2.0 24/96 seems to stream out of the Chromecast Audio as 24/96. However I'm not positive of that. The reason being was with my AVR, the optical interface did not show an incoming stream when I asked CCA to stream 24/96. So I'm suspecting my Onkyo AVR does not support 24/96 PCM via its SPDIF. I do have an SMSL headphone amp that did playback that same 24/96 optical stream but no means of confirming what was actually coming out of the Chromecast other than it saying it was something digital that worked and sounded fine.

### FLAC 5.1 24/96
The normal video chromecast does not work with these files at all. Playback begins to cast and then abruptly stops. On the Chromecast Audio the playback does work OK with 2-channel analog output. I'm assuming it plays only two channels rather than a mix down. The SPDIF output also worked with my headphone amp but I'm not able to confirm what is being output other than my AVR will not play it and my headphone amp will. These files also play via Google Home devices so I'm suspecting there is a common DAC in use on both the Google Home and Chromecast audio devices. 

I have noticed some playback gaps with these files. The test Pi I'm using is a Pi1B. It's weaker and it may not be upto the task in full. So I don't know if these gaps are the result of issues serving up the FLAC files to the Chromecast or something drectly associated with the Chromecast struggling to handle the larger files. Either way, its not worth crying over because Chromecast Audio or a Google Home device will not be able to anything useful with a 5.1 lossless file. 

If we want 5.1 24/96 playback via Chromecast, the only logical way to see that get realised if it plays via the HDMI variant and streams to the AVR as multichannel PCM. I'm hoping the Chocolate Factory will go this route eventually. It might be something the Chromecast Ultra can do but alas I don't have one to hand.

Sop hope you find this useful for you if yuo are trying to get Volumio to play nice with Chromecast. 
