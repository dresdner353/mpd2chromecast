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

## Possible Issues with Paths
The script assumes all music is served from /mnt on the pi. This seems to be case if the music is mounted locally via SD card or network share. If you have a locally attached USB drive, it's possible it has mounted on /media. That's what happened to me. If that is the case you will have issues.

Internally, moOde refers to these /media mounts as USB/xxxx/xxxx. So to make this work, you will need to add a symbolic link in /mnt

To illustrate, this, see the listed filesystems. The /media/Music IcyB is the mount point of my locally atached USB hard drive. Then I added a symlink in /mnt for "USB" to point at /media. 
```
pi@moode:~ $ df
Filesystem     1K-blocks      Used Available Use% Mounted on
/dev/root        3494608   2696684    623892  82% /
devtmpfs          441232         0    441232   0% /dev
tmpfs             474512         0    474512   0% /dev/shm
tmpfs             474512      7340    467172   2% /run
tmpfs               5120         4      5116   1% /run/lock
tmpfs             474512         0    474512   0% /sys/fs/cgroup
/dev/mmcblk0p1    258095     55363    202732  22% /boot
tmpfs              94900         0     94900   0% /run/user/1000
/dev/sda1      976760832 342495104 634265728  36% /media/Music IcyB
pi@moode:~ $ ls -al /mnt
total 20
drwxr-xr-x  5 root root 4096 Oct 30 10:30 .
drwxr-xr-x 21 root root 4096 Jul  2 17:25 ..
drwxr-xr-x  2 root root 4096 Oct 30 10:24 NAS
drwxr-xr-x  3 root root 4096 Oct 30 08:18 SDCARD
drwxr-xr-x  2 root root 4096 Jul  2 17:17 UPNP
lrwxrwxrwx  1 root root    6 Oct 30 10:30 USB -> /media
pi@moode:~ $
```

To add that symlink use:
```
sudo ln -s /media /mnt/USB
```
That will ensure any additional volumes that mount under /media, will symbolically appear in /mnt/USB and should work fine with the streaming.

**Note:** This issue occurs because the web server running within the python script (Cherrypy) is serving a ip:8000/music web path URL from the physical /mnt file system. So any file it is trying to stream via chromecast must be accesible via /mnt releative to the path that moOde provides.  

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
To stop casting, you can normally either pause playback or clear the playlist. You could also disable the casting permanently by deleting/commenting out the crontab entry. 

However there is an easier way to do this by setting the configured chromecast device to 'off'. 
```
$ ./volumio2chromecast/set_chromecast.py --name 'off'
Setting desired Chromecast to [off]
```
This will cause the script to disconnect from any existing cast device and disable any further attempts to connect to a chromecast until the configured device name is again changed.

