pip install a bunch of shii<br>
run in executable with loaded virtual enviroment for scalability <br>
app is for extracting list of short 3second videos or so, with moving cars<br>
app1 is for creating a giant compilation and uploading to yt<br>
app_42069 does the motion detection but when the picamera waits for the request from the program of a tcp stream containing the full data, bypassing YT<br>
app_both does the same as before, with the tcp stream, but also creates a flask service on port 42069 where the live stream is display'd. also fixed the contemporarity of motion detection and streaming to multiple clients who request the flask webpage. also it's suppsedly easily scalable.<br> 
app_both and app_42069 work with the picamera that streams with the stream_local.sh<br>
also this became a surveillance tool kek<br>
added systemd service<br>
added logging to both.py<br>
added both_multiple<br>
which is same as app both but for multiple source streams. also the streams are statically sourced, so when adding a new strem, also modify the javascript<br>
do write street_cars.service in /etc/systemd/system/street_cars.service<br>
#systemctl enable street_cars.service<br>
#systemctl start street_cars.service<br>
