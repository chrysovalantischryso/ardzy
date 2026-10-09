//! ardzy.rs: the Ardzy board from Rust.   Use it with:  mod ardzy;  (in main.rs)
//!
//!     ardzy::led("green", true);          // status LED: "green", "red" or "ps"
//!     ardzy::beep(0.1);                   // buzzer, seconds
//!     if ardzy::button("ip") { ... }      // true while pressed: "ip" (S2) or "reset" (S1)
//!     let v = ardzy::peek(0x41200000);    // 32-bit FPGA register at an address (Vivado's Address Editor)
//!     ardzy::poke(0x41200000, 5);
//!     ardzy::reg(1, 3); ardzy::reg_write(1, 3, 42);   // word 3 of slot 1 of an Ardzy FPGA project
//!     ardzy::watch("speed", 12.5);        // a live value for the app's Watch tab and Plotter
//!
//! Only use FPGA registers that the loaded FPGA design really has: reading an address with nothing
//! behind it can hang the board until it is reset.
#![allow(dead_code)]

use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::os::raw::{c_int, c_void};
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::io::IntoRawFd;
use std::sync::Mutex;
use std::{thread, time::Duration};

pub const BUS_BASE: u32 = 0x43C0_0000; // the register window of Ardzy FPGA projects (16 slots of 4 KB)

fn gpio_set(n: u32, v: bool) {
    fs::write(format!("/sys/class/gpio/gpio{}/value", n), if v { "1" } else { "0" })
        .unwrap_or_else(|e| panic!("gpio{}: {}", n, e));
}

fn gpio_get(n: u32) -> bool {
    let s = fs::read_to_string(format!("/sys/class/gpio/gpio{}/value", n)).unwrap_or_else(|e| panic!("gpio{}: {}", n, e));
    s.starts_with('1')
}

/// Switch a board LED: "green", "red" or "ps".
pub fn led(name: &str, on: bool) {
    match name {
        "green" => gpio_set(38, on),
        "red" => gpio_set(37, on),
        "ps" => gpio_set(15, !on), // the PS LED is on when the pin is low
        _ => panic!("led: green, red or ps"),
    }
}

/// Sound the buzzer for a moment.
pub fn beep(seconds: f64) {
    gpio_set(39, true);
    thread::sleep(Duration::from_secs_f64(seconds));
    gpio_set(39, false);
}

/// True while the button is pressed: "ip" (S2) or "reset" (S1).
pub fn button(name: &str) -> bool {
    match name {
        "ip" => !gpio_get(51),
        "reset" => !gpio_get(47),
        _ => panic!("button: ip or reset"),
    }
}

extern "C" {
    fn mmap64(addr: *mut c_void, len: usize, prot: c_int, flags: c_int, fd: c_int, off: i64) -> *mut c_void;
}
const PROT_RW: c_int = 3; // PROT_READ | PROT_WRITE
const MAP_SHARED: c_int = 1;
const O_SYNC: i32 = 0o4010000;

struct Mem {
    fd: c_int,
    pages: HashMap<u32, usize>,
}
static MEM: Mutex<Option<Mem>> = Mutex::new(None);

fn reg_ptr(addr: u32) -> *mut u32 {
    assert!(addr & 3 == 0, "register addresses are multiples of 4");
    let page = addr & !0xfff;
    let mut g = MEM.lock().unwrap();
    let m = g.get_or_insert_with(|| {
        let f = OpenOptions::new().read(true).write(true).custom_flags(O_SYNC).open("/dev/mem")
            .unwrap_or_else(|e| panic!("/dev/mem: {}", e));
        Mem { fd: f.into_raw_fd(), pages: HashMap::new() }
    });
    let fd = m.fd;
    let base = *m.pages.entry(page).or_insert_with(|| {
        let p = unsafe { mmap64(std::ptr::null_mut(), 4096, PROT_RW, MAP_SHARED, fd, page as i64) };
        assert!(p as isize != -1, "mmap failed");
        p as usize
    });
    (base + (addr & 0xfff) as usize) as *mut u32
}

/// Read a 32-bit register.
pub fn peek(addr: u32) -> u32 {
    unsafe { std::ptr::read_volatile(reg_ptr(addr)) }
}

/// Write a 32-bit register.
pub fn poke(addr: u32, value: u32) {
    unsafe { std::ptr::write_volatile(reg_ptr(addr), value) }
}

/// Word `word` of slot `slot` of an Ardzy FPGA project.
pub fn reg(slot: u32, word: u32) -> u32 {
    peek(BUS_BASE + slot * 0x1000 + 4 * word)
}

pub fn reg_write(slot: u32, word: u32, value: u32) {
    poke(BUS_BASE + slot * 0x1000 + 4 * word, value)
}

/// Show a value live in the app (Watch tab, Plotter).
pub fn watch<T: std::fmt::Display>(name: &str, value: T) {
    println!("{}:{}", name, value);
}
