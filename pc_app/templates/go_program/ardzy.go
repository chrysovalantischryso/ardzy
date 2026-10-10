// ardzy.go: the Ardzy board from Go. It is part of your program (package main), nothing to import.
//
//	Led("green", true)            // status LED: "green", "red" (S9 also "ps")
//	Beep(0.1)                     // buzzer, seconds
//	if Button("ip") { ... }       // true while pressed: "ip" or "reset" (EBAZ4205: also "s2", "s3")
//	v := Peek(0x41200000)         // 32-bit FPGA register at an address (Vivado's Address Editor)
//	Poke(0x41200000, 5)
//	Reg(1, 3); RegWrite(1, 3, 42) // word 3 of slot 1 of an Ardzy FPGA project
//	Watch("speed", 12.5)          // a live value for the app's Watch tab and Plotter
//
// Only use FPGA registers that the loaded FPGA design really has: reading an address with nothing
// behind it can hang the board until it is reset.
package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"syscall"
	"time"
	"unsafe"
)

const BusBase = 0x43C00000 // the register window of Ardzy FPGA projects (16 slots of 4 KB)

type ioPin struct {
	n  int  // Linux GPIO
	on bool // the level that means on / pressed
}

// boardIO: the board's LEDs, buttons and buzzer, from /run/ardzy/board-io.txt (written at boot; every
// Ardzy board has its own). Without it: the Antminer S9.
var boardIO = func() map[string]ioPin {
	io := map[string]ioPin{}
	if b, err := os.ReadFile("/run/ardzy/board-io.txt"); err == nil {
		for _, line := range strings.Split(string(b), "\n") {
			f := strings.Fields(line)
			if len(f) == 3 && !strings.HasPrefix(f[0], "#") {
				if g, err := strconv.Atoi(f[1]); err == nil {
					io[f[0]] = ioPin{g, f[2] == "1"}
				}
			}
		}
	}
	if len(io) == 0 {
		io = map[string]ioPin{"led_green": {38, true}, "led_red": {37, true}, "led_ps": {15, false}, "buzzer": {39, true},
			"button_ip": {51, false}, "button_reset": {47, false}}
	}
	return io
}()

func gpioSet(n int, v bool) {
	s := "0"
	if v {
		s = "1"
	}
	if err := os.WriteFile("/sys/class/gpio/gpio"+strconv.Itoa(n)+"/value", []byte(s), 0644); err != nil {
		panic(err)
	}
}

func gpioGet(n int) bool {
	b, err := os.ReadFile("/sys/class/gpio/gpio" + strconv.Itoa(n) + "/value")
	if err != nil {
		panic(err)
	}
	return len(b) > 0 && b[0] == '1'
}

// Led switches a board LED: "green", "red" (S9 also "ps").
func Led(name string, on bool) {
	l, ok := boardIO["led_"+name]
	if !ok {
		panic("Led: this board has no LED \"" + name + "\" (see /run/ardzy/board-io.txt)")
	}
	gpioSet(l.n, on == l.on)
}

// Beep sounds the buzzer for a moment (a board without a buzzer only waits).
func Beep(seconds float64) {
	b, ok := boardIO["buzzer"]
	if ok {
		gpioSet(b.n, true)
	}
	time.Sleep(time.Duration(seconds * float64(time.Second)))
	if ok {
		gpioSet(b.n, false)
	}
}

// Button is true while the button is pressed: "ip" or "reset" (EBAZ4205: also "s2", "s3").
func Button(name string) bool {
	b, ok := boardIO["button_"+name]
	if !ok {
		panic("Button: this board has no button \"" + name + "\"")
	}
	return gpioGet(b.n) == b.on
}

var memFd = -1
var pages = map[uint32][]byte{}

func regPtr(addr uint32) *uint32 {
	if addr&3 != 0 {
		panic("register addresses are multiples of 4")
	}
	page := addr &^ 0xfff
	m, ok := pages[page]
	if !ok {
		if memFd < 0 {
			fd, err := syscall.Open("/dev/mem", syscall.O_RDWR|syscall.O_SYNC, 0)
			if err != nil {
				panic(err)
			}
			memFd = fd
		}
		var err error
		m, err = syscall.Mmap(memFd, int64(page), 4096, syscall.PROT_READ|syscall.PROT_WRITE, syscall.MAP_SHARED)
		if err != nil {
			panic(err)
		}
		pages[page] = m
	}
	return (*uint32)(unsafe.Pointer(&m[addr&0xfff]))
}

// Peek reads a 32-bit register (atomic: always one real bus access).
func Peek(addr uint32) uint32 { return atomic.LoadUint32(regPtr(addr)) }

// Poke writes a 32-bit register.
func Poke(addr, value uint32) { atomic.StoreUint32(regPtr(addr), value) }

// Reg reads word `word` of slot `slot` of an Ardzy FPGA project.
func Reg(slot, word int) uint32 { return Peek(BusBase + uint32(slot)*0x1000 + 4*uint32(word)) }

// RegWrite writes word `word` of slot `slot`.
func RegWrite(slot, word int, v uint32) { Poke(BusBase+uint32(slot)*0x1000+4*uint32(word), v) }

// Watch shows a value live in the app (Watch tab, Plotter).
func Watch(name string, value interface{}) {
	switch v := value.(type) {
	case string:
		fmt.Printf("%s=%q\n", name, v)
	case bool:
		b := 0
		if v {
			b = 1
		}
		fmt.Printf("%s:%d\n", name, b)
	default:
		fmt.Printf("%s:%v\n", name, v)
	}
}
