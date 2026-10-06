// __NAME__: a C program on the Ardzy board.
// It is compiled on the board (gcc) during the upload, then started.
// printf() output shows up in the Monitor.
#include <stdio.h>
#include <unistd.h>

int main(void)
{
    setvbuf(stdout, NULL, _IOLBF, 0);   // print each line immediately
    for (int n = 0;; n++) {
        printf("hello from __NAME__ (C), count %d\n", n);
        sleep(1);
    }
    return 0;
}
