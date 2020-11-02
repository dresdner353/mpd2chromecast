## Instalation on moOde platforms

Install the related Python3 components:
```
sudo pip3 install pychromecast cherrypy python-mpd2
```

Install the script as follows:
```
cd
git clone https://github.com/dresdner353/volumio2chromecast.git
```

## Adding symbolic links in /mnt
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

**Note:** This issue occurs because the web server running within the python script (Cherrypy) is serving a ip:8000/music web path URL from the physical /mnt file system. So any file it is trying to stream via chromecast must be accesible via /mnt relative to the path that moOde provides.  
