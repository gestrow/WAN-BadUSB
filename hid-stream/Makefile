# Cross-compile hid-stream for Raspberry Pi Zero W (ARMv6)
# Prerequisites: sudo apt install gcc-arm-linux-gnueabihf (in WSL/Linux)

CC = arm-linux-gnueabihf-gcc
CFLAGS = -Wall -Wextra -O2 -static -march=armv6 -mfpu=vfp -mfloat-abi=hard
TARGET = hid-stream
SRC = hid-stream.c

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $(TARGET) $(SRC)

# Native compile (run on the Pi itself)
native:
	gcc -Wall -Wextra -O2 -o $(TARGET) $(SRC)

clean:
	rm -f $(TARGET)

.PHONY: clean native
