# QtStockTicker
by Rob Dobson 2013, updated 2024

## Build

To build an executable:

1) Setup a virtual environment (venv)
2) Activate the venv
3) pip install -r requirements.txt
4) pyinstaller StockTicker.spec --noconfirm

The exe is in the dist folder and the _internal folder is also required to be copied to the required distribution folder

## Configuration File

This should be in the folder privatesettings of the distribution and is a file named stockTickerConfig.json

'''
{
	"FileVersion": 0,
	"ConfigLocations":
	[
	  {
	    "hostURLForGet": "<<url-for-online-or-offline-stocklist>>", "filePathForGet": "/Config/stocklist.json", "getUsing": "local",
        "hostURLForPut": "<<url-for-online-or-offline-stocklist>>", "filePathForPut": "/Config/stocklist.json", "putUsing": "local",
        "userName": "", "passWord" : "", "sourceName": "server"
	  }
	]
}
'''

The ConfigLocations section of this file is a list of configured "backup" locations for the stock list. This can be on a HTTP server for instance.

## Further information

more info at http://robdobson.com/2013/10/a-qt-stock-ticker/

![ScreenShot](https://raw.github.com/robdobsn/QtStockTicker/master/screenshots/latest.png)
