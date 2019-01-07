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
``
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

The script dumps status details each second on the commabnd line as to what is going on. It shows both the status details for Volumio and also for the Chromecast.
