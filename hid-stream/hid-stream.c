/*
 * hid-stream — Fast USB HID keystroke injector for Pi Zero W
 *
 * Usage:
 *   sudo hid-stream                           # interactive mode
 *   sudo hid-stream -t "hello" -k enter       # command-line mode
 *   sudo hid-stream -t "cmd" -k enter -d 50   # with 50ms delay
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <signal.h>
#include <getopt.h>
#include <stdint.h>
#include <ctype.h>
#include <sys/select.h>

#define HID_DEVICE "/dev/hidg0"
#define DEFAULT_DELAY_MS 10

static int hid_fd = -1;
static struct termios orig_termios;
static int raw_mode_active = 0;

/* ---- HID keymap (matches hid.py) ---- */

struct char_entry {
    char ch;
    uint8_t keycode;
    uint8_t modifier;
};

static const struct char_entry CHARMAP[] = {
    {'a', 0x04, 0x00}, {'b', 0x05, 0x00}, {'c', 0x06, 0x00}, {'d', 0x07, 0x00},
    {'e', 0x08, 0x00}, {'f', 0x09, 0x00}, {'g', 0x0A, 0x00}, {'h', 0x0B, 0x00},
    {'i', 0x0C, 0x00}, {'j', 0x0D, 0x00}, {'k', 0x0E, 0x00}, {'l', 0x0F, 0x00},
    {'m', 0x10, 0x00}, {'n', 0x11, 0x00}, {'o', 0x12, 0x00}, {'p', 0x13, 0x00},
    {'q', 0x14, 0x00}, {'r', 0x15, 0x00}, {'s', 0x16, 0x00}, {'t', 0x17, 0x00},
    {'u', 0x18, 0x00}, {'v', 0x19, 0x00}, {'w', 0x1A, 0x00}, {'x', 0x1B, 0x00},
    {'y', 0x1C, 0x00}, {'z', 0x1D, 0x00},
    {'A', 0x04, 0x02}, {'B', 0x05, 0x02}, {'C', 0x06, 0x02}, {'D', 0x07, 0x02},
    {'E', 0x08, 0x02}, {'F', 0x09, 0x02}, {'G', 0x0A, 0x02}, {'H', 0x0B, 0x02},
    {'I', 0x0C, 0x02}, {'J', 0x0D, 0x02}, {'K', 0x0E, 0x02}, {'L', 0x0F, 0x02},
    {'M', 0x10, 0x02}, {'N', 0x11, 0x02}, {'O', 0x12, 0x02}, {'P', 0x13, 0x02},
    {'Q', 0x14, 0x02}, {'R', 0x15, 0x02}, {'S', 0x16, 0x02}, {'T', 0x17, 0x02},
    {'U', 0x18, 0x02}, {'V', 0x19, 0x02}, {'W', 0x1A, 0x02}, {'X', 0x1B, 0x02},
    {'Y', 0x1C, 0x02}, {'Z', 0x1D, 0x02},
    {'1', 0x1E, 0x00}, {'2', 0x1F, 0x00}, {'3', 0x20, 0x00}, {'4', 0x21, 0x00},
    {'5', 0x22, 0x00}, {'6', 0x23, 0x00}, {'7', 0x24, 0x00}, {'8', 0x25, 0x00},
    {'9', 0x26, 0x00}, {'0', 0x27, 0x00},
    {'!', 0x1E, 0x02}, {'@', 0x1F, 0x02}, {'#', 0x20, 0x02}, {'$', 0x21, 0x02},
    {'%', 0x22, 0x02}, {'^', 0x23, 0x02}, {'&', 0x24, 0x02}, {'*', 0x25, 0x02},
    {'(', 0x26, 0x02}, {')', 0x27, 0x02},
    {'\n', 0x28, 0x00}, {'\t', 0x2B, 0x00}, {' ', 0x2C, 0x00},
    {'-', 0x2D, 0x00}, {'=', 0x2E, 0x00}, {'[', 0x2F, 0x00}, {']', 0x30, 0x00},
    {'\\', 0x31, 0x00}, {';', 0x33, 0x00}, {'\'', 0x34, 0x00}, {'`', 0x35, 0x00},
    {',', 0x36, 0x00}, {'.', 0x37, 0x00}, {'/', 0x38, 0x00},
    {'_', 0x2D, 0x02}, {'+', 0x2E, 0x02}, {'{', 0x2F, 0x02}, {'}', 0x30, 0x02},
    {'|', 0x31, 0x02}, {':', 0x33, 0x02}, {'"', 0x34, 0x02}, {'~', 0x35, 0x02},
    {'<', 0x36, 0x02}, {'>', 0x37, 0x02}, {'?', 0x38, 0x02},
    {0, 0, 0} /* sentinel */
};

struct special_entry {
    const char *name;
    uint8_t keycode;
    uint8_t modifier;
};

static const struct special_entry SPECIAL_KEYS[] = {
    {"enter",     0x28, 0x00}, {"return",    0x28, 0x00},
    {"esc",       0x29, 0x00}, {"escape",    0x29, 0x00},
    {"backspace", 0x2A, 0x00}, {"tab",       0x2B, 0x00},
    {"space",     0x2C, 0x00}, {"capslock",  0x39, 0x00},
    {"f1",        0x3A, 0x00}, {"f2",        0x3B, 0x00},
    {"f3",        0x3C, 0x00}, {"f4",        0x3D, 0x00},
    {"f5",        0x3E, 0x00}, {"f6",        0x3F, 0x00},
    {"f7",        0x40, 0x00}, {"f8",        0x41, 0x00},
    {"f9",        0x42, 0x00}, {"f10",       0x43, 0x00},
    {"f11",       0x44, 0x00}, {"f12",       0x45, 0x00},
    {"insert",    0x49, 0x00}, {"home",      0x4A, 0x00},
    {"pageup",    0x4B, 0x00}, {"delete",    0x4C, 0x00},
    {"end",       0x4D, 0x00}, {"pagedown",  0x4E, 0x00},
    {"right",     0x4F, 0x00}, {"left",      0x50, 0x00},
    {"down",      0x51, 0x00}, {"up",        0x52, 0x00},
    {"ctrl+a",    0x04, 0x01}, {"ctrl+c",    0x06, 0x01},
    {"ctrl+v",    0x19, 0x01}, {"ctrl+x",    0x1B, 0x01},
    {"ctrl+z",    0x1D, 0x01}, {"ctrl+s",    0x16, 0x01},
    {"ctrl+l",    0x0F, 0x01}, {"ctrl+r",    0x15, 0x01},
    {"alt+tab",   0x2B, 0x04}, {"alt+f4",    0x3D, 0x04},
    {"win",       0x00, 0x08}, {"gui",       0x00, 0x08},
    {"win+r",     0x15, 0x08}, {"win+e",     0x08, 0x08},
    {"win+d",     0x07, 0x08},
    {NULL, 0, 0} /* sentinel */
};

/* ---- HID report I/O ---- */

static int send_report(uint8_t modifier, uint8_t keycode) {
    uint8_t report[8] = {modifier, 0, keycode, 0, 0, 0, 0, 0};
    uint8_t release[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    if (write(hid_fd, report, 8) != 8) return -1;
    if (write(hid_fd, release, 8) != 8) return -1;
    return 0;
}

static int find_char(char c, uint8_t *keycode, uint8_t *modifier) {
    for (int i = 0; CHARMAP[i].ch != 0; i++) {
        if (CHARMAP[i].ch == c) {
            *keycode = CHARMAP[i].keycode;
            *modifier = CHARMAP[i].modifier;
            return 0;
        }
    }
    return -1;
}

static int find_special(const char *name, uint8_t *keycode, uint8_t *modifier) {
    for (int i = 0; SPECIAL_KEYS[i].name != NULL; i++) {
        if (strcasecmp(SPECIAL_KEYS[i].name, name) == 0) {
            *keycode = SPECIAL_KEYS[i].keycode;
            *modifier = SPECIAL_KEYS[i].modifier;
            return 0;
        }
    }
    return -1;
}

static void type_string(const char *text, int delay_ms) {
    uint8_t keycode, modifier;
    for (int i = 0; text[i] != '\0'; i++) {
        if (find_char(text[i], &keycode, &modifier) == 0) {
            send_report(modifier, keycode);
            if (delay_ms > 0)
                usleep(delay_ms * 1000);
        }
    }
}

static void send_special_key(const char *name) {
    uint8_t keycode, modifier;
    if (find_special(name, &keycode, &modifier) == 0) {
        send_report(modifier, keycode);
    } else {
        fprintf(stderr, "unknown key: %s\n", name);
    }
}

/* ---- Terminal raw mode ---- */

static void restore_terminal(void) {
    if (raw_mode_active) {
        tcsetattr(STDIN_FILENO, TCSAFLUSH, &orig_termios);
        raw_mode_active = 0;
    }
}

static void enter_raw_mode(void) {
    tcgetattr(STDIN_FILENO, &orig_termios);
    atexit(restore_terminal);

    struct termios raw = orig_termios;
    raw.c_iflag &= ~(BRKINT | ICRNL | INPCK | ISTRIP | IXON);
    raw.c_oflag &= ~(OPOST);
    raw.c_cflag |= (CS8);
    raw.c_lflag &= ~(ECHO | ICANON | IEXTEN | ISIG);
    raw.c_cc[VMIN] = 1;
    raw.c_cc[VTIME] = 0;

    tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw);
    raw_mode_active = 1;
}

/* Read a byte with timeout (for ESC sequences). Returns -1 on timeout. */
static int read_byte_timeout(int timeout_ms) {
    fd_set fds;
    struct timeval tv;
    FD_ZERO(&fds);
    FD_SET(STDIN_FILENO, &fds);
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;
    if (select(STDIN_FILENO + 1, &fds, NULL, NULL, &tv) > 0) {
        unsigned char c;
        if (read(STDIN_FILENO, &c, 1) == 1)
            return c;
    }
    return -1;
}

static void signal_handler(int sig) {
    (void)sig;
    restore_terminal();
    if (hid_fd >= 0) close(hid_fd);
    _exit(0);
}

/* ---- Interactive mode ---- */

static void interactive_mode(int delay_ms) {
    enter_raw_mode();
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    printf("hid-stream interactive mode\r\n");
    printf("  type normally — keystrokes sent to target\r\n");
    printf("  ESC q — quit\r\n");
    printf("  arrow keys, home, end, delete work\r\n\r\n");

    uint8_t keycode, modifier;

    while (1) {
        unsigned char c;
        if (read(STDIN_FILENO, &c, 1) != 1)
            break;

        if (c == 0x1b) { /* ESC */
            int next = read_byte_timeout(100);
            if (next == -1) {
                /* bare ESC — send ESC key */
                send_report(0x00, 0x29);
            } else if (next == '[') {
                int seq = read_byte_timeout(100);
                switch (seq) {
                    case 'A': send_report(0x00, 0x52); break; /* up */
                    case 'B': send_report(0x00, 0x51); break; /* down */
                    case 'C': send_report(0x00, 0x4F); break; /* right */
                    case 'D': send_report(0x00, 0x50); break; /* left */
                    case 'H': send_report(0x00, 0x4A); break; /* home */
                    case 'F': send_report(0x00, 0x4D); break; /* end */
                    case '3': /* delete (ESC [ 3 ~) */
                        if (read_byte_timeout(100) == '~')
                            send_report(0x00, 0x4C);
                        break;
                    case '5': /* page up (ESC [ 5 ~) */
                        if (read_byte_timeout(100) == '~')
                            send_report(0x00, 0x4B);
                        break;
                    case '6': /* page down (ESC [ 6 ~) */
                        if (read_byte_timeout(100) == '~')
                            send_report(0x00, 0x4E);
                        break;
                    default:
                        break;
                }
            } else if (next == 'q' || next == 'Q') {
                printf("\r\nquitting.\r\n");
                break;
            }
        } else if (c == 0x03) {
            /* Ctrl+C — send HID ctrl+c */
            send_report(0x01, 0x06);
        } else if (c == 0x04) {
            /* Ctrl+D — quit */
            printf("\r\nquitting.\r\n");
            break;
        } else if (c == 0x7f || c == 0x08) {
            /* Backspace */
            send_report(0x00, 0x2A);
        } else if (c == '\r') {
            /* Enter (terminal sends \r in raw mode) */
            send_report(0x00, 0x28);
        } else if (find_char((char)c, &keycode, &modifier) == 0) {
            send_report(modifier, keycode);
        }

        if (delay_ms > 0)
            usleep(delay_ms * 1000);
    }
}

/* ---- Usage ---- */

static void usage(void) {
    printf("Usage: hid-stream [options]\n");
    printf("  No arguments: interactive mode (type keystrokes in real-time)\n\n");
    printf("Options:\n");
    printf("  -t TEXT    Type a text string\n");
    printf("  -k KEY     Send a special key (enter, ctrl+c, win+r, etc.)\n");
    printf("  -d MS      Set inter-key delay in milliseconds (default: %d)\n", DEFAULT_DELAY_MS);
    printf("  -h         Show this help\n\n");
    printf("Examples:\n");
    printf("  sudo hid-stream -t 'hello world' -k enter\n");
    printf("  sudo hid-stream -k win+r -d 500 -t 'cmd' -k enter\n");
    printf("  sudo hid-stream   # interactive\n\n");
    printf("Special keys: enter, esc, backspace, tab, space, delete,\n");
    printf("  home, end, pageup, pagedown, up, down, left, right,\n");
    printf("  f1-f12, ctrl+a/c/v/x/z/s/l/r, alt+tab, alt+f4,\n");
    printf("  win, win+r, win+e, win+d\n");
}

/* ---- Main ---- */

/*
 * We process argv manually instead of using getopt in a loop because
 * -t and -k can be interleaved and order matters:
 *   hid-stream -k win+r -d 500 -t "cmd" -k enter
 * means: send win+r, change delay to 500ms, type "cmd", send enter.
 */
int main(int argc, char *argv[]) {
    int delay_ms = DEFAULT_DELAY_MS;
    int has_actions = 0;

    /* Check for -h first */
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            usage();
            return 0;
        }
    }

    /* Open HID device */
    hid_fd = open(HID_DEVICE, O_WRONLY);
    if (hid_fd < 0) {
        perror("open " HID_DEVICE);
        fprintf(stderr, "hint: run as root (sudo hid-stream)\n");
        return 1;
    }

    /* If no action args, enter interactive mode */
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-t") == 0 || strcmp(argv[i], "-k") == 0) {
            has_actions = 1;
            break;
        }
    }

    if (!has_actions) {
        interactive_mode(delay_ms);
        close(hid_fd);
        return 0;
    }

    /* Command-line mode: process args left-to-right */
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-t") == 0 && i + 1 < argc) {
            i++;
            type_string(argv[i], delay_ms);
        } else if (strcmp(argv[i], "-k") == 0 && i + 1 < argc) {
            i++;
            send_special_key(argv[i]);
            if (delay_ms > 0)
                usleep(delay_ms * 1000);
        } else if (strcmp(argv[i], "-d") == 0 && i + 1 < argc) {
            i++;
            delay_ms = atoi(argv[i]);
        }
    }

    close(hid_fd);
    return 0;
}
