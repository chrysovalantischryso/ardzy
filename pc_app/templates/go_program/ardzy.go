// ardzy.go: the Ardzy board from Go. It is part of your program (package main), nothing to import.
//
//	Led("green", true)            // status LED: "green", "red" or "ps"
//	Beep(0.1)                     // buzzer, seconds
//	if Button("ip") { ... }       // true while pressed: "ip" (S2) or "reset" (S1)
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
	"sync/atomic"
	"syscall"
	"time"
	"unsafe"
)

const BusBase = 0x43C00000 // the register window of Ardzy FPGA projects (16 slots of 4 KB)

var ledPins = map[string]struct {
	n      int
	onHigh bool
}{"green": {38, true}, "red": {37, true}, "ps": {15, false}}
var buttonPins = map[string]int{"ip": 51, "reset": 47}

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

// Led switches a board LED: "green", "red" or "ps".
func Led(name string, on bool) {
	l, ok := ledPins[name]
	if !ok {
		panic("Led: green, red or ps")
	}
	gpioSet(l.n, on == l.onHigh)
}

// Beep sounds the buzzer for a moment.
func Beep(seconds float64) {
	gpioSet(39, true)
	time.Sleep(time.Duration(seconds * float64(time.Second)))
	gpioSet(39, false)
}

// Button is true while the button is pressed: "ip" (S2) or "reset" (S1).
func Button(name string) bool {
	n, ok := buttonPins[name]
	if !ok {
		panic("Button: ip or reset")
	}
	return !gpioGet(n)
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
