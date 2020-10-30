## moode2chromecast

Variation of the Volumio script adapted for moOde. 

## Installation

Install the related Python3 components:
```
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
LC_ALL=en_US.UTF-8  ~/volumio2chromecast/moode2chromecast.py 
```
In this mode, the script will output data every second showing moOde playback status and any related activity from the Chromecast. Once you have the script running, it should start trying to cast the current playlist to the selected chromecast. Try changing tracks, pausing, skipping and changing volume and you should see the Chromecast react pretty quickly.

Note: The use of LC_ALL set to US UTF-8 was something I was forced to do because when left on my default locale (Ireland UTF-8), something went wrong with how UTF-8 characters we being matched between filenames on the disk and the URLs. I suspect it relates to locale specifics not present within the Raspian image. Forcing US UTF-8 sorts this however.

## Starting the Agent in the Background

To start the agent in the background, use this command:
```
./volumio2chromecast/moodechromecast.sh
```
You can also force a restart of the agent using the "restart" option:
```
./volumio2chromecast/volumio2chromecast.sh restart
```

## Enabling the script to run at startup
The shell script mentioned above is crontab friendly in that it can be invoked continually and will only start the agent if it's not found to be running. 

To setup crontab on the Pi (it's possibly not running by default):
```
sudo update-rc.d cron enable 2 3 4 5
sudo /etc/init.d/cron start
   
crontab -e 
    .. when prompted, select the desired editor and add this line:
    * * * * * /home/pi/volumio2chromecast/moode2chromecast.sh > /dev/null

```

## Dynamically switching Chromecast
When using the saved config approach, the script watches the ~/.castrc file for changes. If it detects a change, it reloads config, re-resolves the Chromecast and switches device. It will also try to stop playback on the current device.

All you need to do is run the set_chromecast.py script and specify the new device or select from its menu. Once saved, the playback should switch devices in about 10-20 seconds, giving time for the change to be detected and discovery of the new device to take place.

## Disabling
To stop casting, you can normally either pause playback or clear the playlist. You could also disable the casting permanently by disabling the crontab entry. 

However there is an easier way to do this by setting the configured chromecast device to 'off'. 
```
$ ./volumio2chromecast/set_chromecast.py --name 'off'
Setting desired Chromecast to [off]
```
This will cause the script to disconnect from any existing cast device and disable any further attempts to connect to a chromecast until the configured device name is again changed.

