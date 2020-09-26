# ESP-Player

A [qrpr](qrpr.eu/) player that can be server localy from your esp32 device running [MicroPython](https://micropython.org/)!

## Using

1. install micropython on your esp32 device
2. run `./flash.sh`, first flash can take several minutes to complete
3. connect to the `QRGames Player` WiFi
4.  enter any http:// URL
5. get redirected to the [http://qrpr.eu](http://qrpr.eu)
6. profit

## How it works?

The esp32 acts as a captive portal by rewriting all DNS requests to its own IP address and then serves locally cached copy of the website.

## Origins

[DNS rewriting mechanism](https://github.com/amora-labs/micropython-captive-portal) was originally made by amora-labs and licensed under MIT.