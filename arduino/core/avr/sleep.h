/* avr/sleep.h - compatibility: sleeping is done by Linux. */
#pragma once
#define SLEEP_MODE_IDLE 0
#define SLEEP_MODE_PWR_DOWN 2
#define set_sleep_mode(m) ((void)(m))
#define sleep_enable()
#define sleep_disable()
#define sleep_cpu() delay(1)
#define sleep_mode() delay(1)
