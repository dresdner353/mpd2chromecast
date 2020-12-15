## mpd2chromecast

This is a python script and related shell wrapper that you can deploy on a Volumio or moOde installation and use it to integrate single and multi-room playback with Google Chromecast devices and all variants such as Google/Nest Home speakers.

The script uses an MPD client to monitor playback state of MPD, the underlying media player layer used by both Volumio and moOde. It then generates and sends a URL for the playing file to the target chromecast device or group. The chromecast then streams the file contents and plays the file. 

As you invoke play, stop, pause, next/previous, seek actions & volume control on your media platform, these are detected by the MPD interface and then relayed to the Chromecast to match the behaviour. The script also provides album artwork support that will appear on screen for video-based chromecasts.

**Note:** Does not work on the official Volumio Jesse-based images any longer. The Jesse release is over 5 years old and too old to keep up with various Python dependencies. It does work however on their beta images for Raspian Buster. So this limitation will go away once Volumio get official images released for Buster.

**Note:** MPD Volume control needs to be enabled for this script to then relay that value to the chromecast. If your MPD setup via Volumio or moOde is set to not allow MPD volume control or has software/hardware disabled, it may result in MPD not reporting a volume level. When this happens, the script will disable its volume support.

## Acknowledgements
The script would not be possible without the dedicated hard work of others who wrote various modules that made my job a lot easier:

* python-mp2 (https://github.com/Mic92/python-mpd2)  
This module implements an MPD client API that made everything very consistent. Prior to using this module, I was talking directly to the Volumio and moOde APIs but this approach is a lot better.

* pychromecast (https://github.com/balloob/pychromecast)  
With this module, we are able to detect and control Chromecast-based devices on the LAN.

* cherrypy (cherrypy.org)  
All URL serving provided by this script is made possible by the cherrypy module. Python does come with it's own HTTP libraries for client and server but they can be quite complex when playing a web server role. Cherrypy provides a much more mature and reliable framework for providing a directory URL server needed for the media and albumart files.

## Installation
ssh into your user account:
```
ssh volumio@volumio.local
or 
ssh pi@moode.local
```
Then start the install process as follows (you will be prompted for the password for sudo):
```
curl -s https://raw.githubusercontent.com/dresdner353/mpd2chromecast/master/install.sh | sudo bash
```
This command will:
* Install required packages..  
pip3, cron, pychromecast cherrypy python-mpd2 mutagen
* Enable cron (scheduler)  
* Download mpd2chromecast  
* Enable cronjob to auto-start mpd2chromecast  

## Web Interface
![Cast Control Web Interface](./cast_web_control.jpg)

Browse to http://[your device ip]:8090/cast and you will see a very simple web interface for managing the cast devices. The first drop-down combo shows all discovered chromecast devices. Select the desired device and it will set that as the active cast device. 

Once you have selected the desired chromecast, playback should start trying to cast the current track to the selected chromecast. From you preferred UI (Volumio or Moode Web I/F, MPD client, apps etc), try playing tracks, playlists, changing tracks, pausing, skipping and changing volume and you should see the Chromecast react pretty quickly as the script detects local MPD playback changes and casts the new tracks.

Switch chromecast device and you should experience playback stopping on the current device and transferring to the new device. By setting the device to 'Disabled', you will disable the casting functionality. 

The web interface also allows you to select stored playlists (MPD playlists only) as well as select tracks from the current queue. You can also change volume, skip forward/backward on tracks and toggle the shuffle, repeat and playlist consume modes. It's incredibly bland as an interface but I wanted to extend the features a little bit given the script is acting as an MPD client. It even shows albumart and the current playing title.

It's built with Bootstrap and jquery and under normal running, updates its content each time you perform an action or every 10 seconds. The updating is suspended when the browser window/tab is not in focus. It's use is best suited for mobile or tablet devices. It will work on a normal computer browser but the controls and artwork may appear quite large due to the responsive design scaling to the larger window. 

When using Volumio, be aware that the MPD queue only shows one track at a time as Volumio manages its own playlist outside of MPD. This has a knock-on effect with this web UI as it will only show a single playing track in the queue drop-down. You can however use an MPD client to still create and manage playlists on your Volumio server and use this web client to select those playlists for playback.

## How it works
The script runs four threads:
* MPD/Chromecast  
This is to monitor the playback state of the server via MPD API allowing us to know what is playing and react to track changes, volume, pause/play/skip etc. It then passes these directives to the configured chromecast. It also monitors the chromecast status to ensure playback is operational. An albumart link is also passed if available.

* Cherrypy (web server)  
This thread provides a simple web server which is used to serve a file and albumart URLs for each track. It listens on port 8090 serving music URLs from /music. The chromecasts will use the URLs to stream the files for native playback. The same server is also used to provide the control interface hosted on /cast allowing a user to select a desired cast device from a list of discovered devices.

* Config  
This thread just monitors config (~/.castrc) and changes one internal global variable for the selected chromecast device.

* Chromecast Discovery  
This thread runs on loop every minute, scanning for available chromecasts and uses the details to obtain API handles on the desired chromecast for streaming. 

## Audio file types that work
MPD will handle a wide range of files natively and work with attached DACs, HDMI or USB interfaces that can handle it. Bear in mind however that we are totally bypassing this layer and serving a file URL directly to the Chromecast and all decoding is done by the Chromecast.

### MP3 16/320kbps & FLAC 2.0 16/44
I've had perfect results on all variants of Chromecast (Video, Audio and Home) with standard MP3 320, aac files (Apple m4a) and FLAC 2.0 16/44. I did not try ogg or raw WAV 16/44 but assume it would also work.

### FLAC 2.0 24/96
For 2-channel 24/96 high-res, the standard HD & 4K video Chromecasts will play them back but I've noticed it streams into my AVR via HDMI as 48Khz. The same 2.0 24/96 seems to stream out of the Chromecast Audio as a SPDIF digital bitstream.

### FLAC 5.1 24/96
The standard video chromecast does not work with these files at all. Playback begins to cast and then abruptly stops. On the Chromecast Audio the playback does work but with 2-channel analog output. I'm assuming it plays only two channels rather than a mix down. These files also play via Google Home devices so I'm suspecting there is a common DAC in use on both the Google Home and Chromecast audio devices. 

## Albumart & The Default Media Receiver
The standard Chromecasts, integrated TV devices and Nest Hub devices have a screen on hand. So it was obviously a goal to get albumart functional as the default media receiver can display it.

Example of how this albumart appears:
![Chromecast Default Media Receiver](./cc_default_media_receiver.jpg)

The title of the current track is shown on the left. That is the only editable text field available to us. The main nuisance is the 'Default Media Receiver' text. There have been requests in the past for Google to remove this or make it editable via metadata in the cast API. To date they have not changed it. It's not easy to see in the image but a larger version of the album art is also faintly displayed in the overall background of the screen.

Getting albumart proved a bit cumbersome. MPD support via python-mpd2 is not yet working (although it seems to be present in the code). Both Volumio and moOde have their own ways of extracting album art separate from MPD but neither make it seamless to grab this data via native APIs. The main issue was timing where the native API is not always in sync with the MPD playlist. It became a hit and miss in getting accurate albumart with the wrong image often being served up. 

So in the end, to keep things more universal, I copied what MPD server-side itself does... when a track is being cast, the script checks the parent directory of the said file and checks for cover.(png|jpg|tiff|bmp|gif). If that file is found, it generates a URL for this file and serves it to the Chromecast along with the audio file URL. 

## Extracting Albumart from your files
Not everyone will have a cover.XXX file in each album folder. I've always tried to embed artwork into my ripped flac and mp3 files. So I wrote an assistant python script (extract_albumart.py) which uses the Python mutagen module to scan a filesystem of music files, test for non-presence of cover.XXX files and then try to extract the first image from the first music file it finds in each directory. It's not a guaranteed scenario expecially if separate artwork exists per file, but its a decent shot at filling in the gaps.

To use the script, you would need to have your music resource mounted in read-write mode. This may be fine for attached USB storage but bear in mind, if trying this with a NAS mount, you would need to modify the mount settings, ensuring the "rw" option is added.

The script is invoked as follows:
```
sudo pip3 install mutagen 
python3 mpd2chromecast/extract_albumart.py --mpd_dir /var/lib/mpd/music
```
The --mpd_dir option specifies the root directory to start from. If omitted, it defaults to /var/lib/mpd/music. You can set this to any mount point on the system and could test it on a smaller sub-directory initially. 

When the script exits, it will report the total number of directories scanned, and covers it created or faied to create

## Conclusions
So I hope you find this useful if you are trying to get Volumio, moOde etc to play nice with Chromecast. 
