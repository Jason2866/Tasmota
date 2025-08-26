Import("env")

env.Replace(UPLOADER="scp")
env.Replace(UPLOADERFLAGS="")
env.Replace(UPLOADCMD='$UPLOADER $SOURCES "$UPLOAD_PORT/${PIOENV}.bin"')
