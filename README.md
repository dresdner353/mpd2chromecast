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
sudo pip3 install pychromecast cherrypy
```

As volumio user, install the script as follows:

```
cd
git clone https://github.com/dresdner353/volumio2chromecast.git
```

## Starting the Agent in the Background

You should first run the set_chromecast.py script to perform a scan of the available Chromecast devices on your network and then make your selection by number. For example:
```
volumio@volumio:~$ ./volumio2chromecast/set_chromecast.py
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
volumio@volumio:~$ 
```
This then saves the selected Chronecast name in ~/.castrc.

You can also invoke that script with the --name option to directly set the desired Chromecast without having to scan:
```
volumio@volumio:~$ ./volumio2chromecast/set_chromecast.py --name 'Office'
Setting desired Chromecast to [Office]
volumio@volumio:~$ 
```

Then to start the agent use this command:
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
sudo apt-get install gnome-schedule
   
crontab -e 
    .. when prompted, select the desired editor and add this line:
    * * * * * /home/volumio/volumio2chromecast/volumio2chromecast.sh > /dev/null

```



## How it works
When you run the script it will first do a discovery of your specified Chromecast (if you specified it by --name) to obtain its IP and port. That will take several seconds as it runs the DNS-SD to discover devices. You can alternatively start with the --ip and optional --port options for your target chromecast device.

After determining the IP and port of the target chromecast, the script then runs two threads. One thread manages a webserver which is using cherrypy for the engine. That webserver serves up a file tree from / and is used to serve up URLs generated from the currently playing file.

The other thread is a continuous loop using a 1 second sleep that works between the Volumio current play state and the Chromecast playback state. 

At the console, the script will start showing the current Volumio JSON state every second. It gets this by calling the RESTful API function http://localhost:3000/api/v1/getstate

If it detects that something is playing, it will generate a URL for the file (using the uri field of the volumio state) and invoke a cast of that file URL to the specified Chromecast. That is where the pychromecast module comes in to drive all interaction with the Chromecast. The Chromecast should then call back to us on the webserver port to stream the URL. It will return at intervals to pull more data from the file as the playback progresses.

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

So I hope you find this useful for you if yuo are trying to get Volumio to play nice with Chromecast. 
