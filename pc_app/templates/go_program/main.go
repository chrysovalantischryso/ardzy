// __NAME__: a Go program on the Ardzy board.
// Press Upload: it is compiled on the board (go build) and started; fmt.Println output shows up in the Monitor.
// The very first Go build on a board takes one to three minutes (Go compiles its own library once); later ones take seconds.
// ardzy.go has the board: Led, Beep, Button, Peek/Poke (FPGA registers), Watch.
//   - the green status LED blinks
//   - press the IP button (S2): a beep, and the count goes up (see it in the Watch tab)
//   - press the Reset button (S1): the program ends
package main

import (
	"fmt"
	"time"
)

func main() {
	fmt.Println("hello from __NAME__ (Go): press the IP button, or Reset to end")
	presses := 0
	for t := 0; ; t++ {
		Led("green", t%10 < 5)
		if Button("ip") {
			presses++
			fmt.Printf("IP button pressed (%d)\n", presses)
			Watch("presses", presses)
			Beep(0.08)
			for Button("ip") { // wait until it is released
				time.Sleep(20 * time.Millisecond)
			}
		}
		if Button("reset") {
			fmt.Println("Reset button pressed: bye!")
			Beep(0.4)
			break
		}
		// An FPGA register (only with an FPGA design that has it), for example:
		//   v := Reg(1, 0)
		time.Sleep(100 * time.Millisecond)
	}
	Led("green", false)
}
