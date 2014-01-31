FlexgetConfig
=============

Configuration for Flexget

Note that all sensitive info (RSS feed URLs, deluge auth, etc.) has either been scrubbed using .gitattributes or has been moved into separate files in an includes/ directory (which will not be committed). The only things not visible in the config file are a standard use of the ```rss``` plugin (```rss: http://tracker.example.com/rss.feed```) and two instances of the ```from_trakt``` plugin to retrieve custom lists from [trakt.tv](http://trakt.tv).

aria2 Plugin
============

Documentation for the aria2 plugin that I contributed to Flexget can be found [here](https://github.com/tubedogg/.flexget/tree/master/plugins).