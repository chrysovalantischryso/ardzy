//! ardzy.rs: the Ardzy board from Rust.   Use it with:  mod ardzy;  (in main.rs)
//!
//!     ardzy::led("green", true);          // status LED: "green", "red" (S9 also "ps")
//!     ardzy::beep(0.1);                   // buzzer, seconds
//!     if ardzy::button("ip") { ... }      // true while pressed: "ip" or "reset" (EBAZ4205: also "s2", "s3")
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

/// The board's LEDs, buttons and buzzer: name -> (Linux GPIO, the level that means on / pressed), from
/// /run/ardzy/board-io.txt (written at boot; every Ardzy board has its own). Without it: the Antminer S9.
fn board_io() -> &'static HashMap<String, (u32, bool)> {
    static IO: std::sync::OnceLock<HashMap<String, (u32, bool)>> = std::sync::OnceLock::new();
    IO.get_or_init(|| {
        let mut io = HashMap::new();
        if let Ok(text) = fs::read_to_string("/run/ardzy/board-io.txt") {
            for line in text.lines() {
                let f: Vec<&str> = line.split_whitespace().collect();
                if f.len() == 3 && !f[0].starts_with('#') {
                    if let Ok(g) = f[1].parse::<u32>() {
                        io.insert(f[0].to_string(), (g, f[2] == "1"));
                    }
                }
            }
        }
        if io.is_empty() {
            for (n, g, on) in [("led_green", 38, true), ("led_red", 37, true), ("led_ps", 15, false), ("buzzer", 39, true),
                               ("button_ip", 51, false), ("button_reset", 47, false)] {
                io.insert(n.to_string(), (g, on));
            }
        }
        io
    })
}

/// Switch a board LED: "green", "red" (S9 also "ps").
pub fn led(name: &str, on: bool) {
    match board_io().get(&format!("led_{}", name)) {
        Some(&(g, level)) => gpio_set(g, on == level),
        None => panic!("led: this board has no LED \"{}\" (see /run/ardzy/board-io.txt)", name),
    }
}

/// Sound the buzzer for a moment (a board without a buzzer only waits).
pub fn beep(seconds: f64) {
    let b = board_io().get("buzzer").copied();
    if let Some((g, _)) = b {
        gpio_set(g, true);
    }
    thread::sleep(Duration::from_secs_f64(seconds));
    if let Some((g, _)) = b {
        gpio_set(g, false);
    }
}

/// True while the button is pressed: "ip" or "reset" (EBAZ4205: also "s2", "s3").
pub fn button(name: &str) -> bool {
    match board_io().get(&format!("button_{}", name)) {
        Some(&(g, level)) => gpio_get(g) == level,
        None => panic!("button: this board has no button \"{}\"", name),
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
