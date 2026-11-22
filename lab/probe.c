#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static void inspect_files(const char *hidden, const char *input, const char *scratch)
{
    int fd = open(hidden, O_RDONLY);
    printf("hidden_errno=%d\n", fd < 0 ? errno : 0);
    if (fd >= 0)
        close(fd);

    char buffer[16] = {0};
    fd = open(input, O_RDONLY);
    ssize_t bytes = fd < 0 ? -1 : read(fd, buffer, sizeof buffer - 1);
    printf("input_read=%d\n", bytes >= 6 && memcmp(buffer, "PUBLIC", 6) == 0);
    if (fd >= 0)
        close(fd);

    fd = open(input, O_WRONLY);
    printf("input_write_errno=%d\n", fd < 0 ? errno : 0);
    if (fd >= 0)
        close(fd);

    fd = open(scratch, O_WRONLY | O_CREAT | O_EXCL, 0600);
    printf("scratch_errno=%d\n", fd < 0 ? errno : 0);
    if (fd >= 0) {
        close(fd);
        unlink(scratch);
    }
}

static int inspect_processes(const char *marker)
{
    DIR *proc = opendir("/proc");
    if (!proc)
        return 2;

    bool visible = false;
    struct dirent *entry;
    while ((entry = readdir(proc)) != NULL) {
        if (strspn(entry->d_name, "0123456789") != strlen(entry->d_name))
            continue;

        char path[PATH_MAX];
        snprintf(path, sizeof path, "/proc/%s/comm", entry->d_name);
        FILE *file = fopen(path, "r");
        if (file) {
            char name[32];
            if (fgets(name, sizeof name, file)) {
                name[strcspn(name, "\n")] = '\0';
                visible |= strcmp(name, marker) == 0;
            }
            fclose(file);
        }
    }
    closedir(proc);
    printf("sentinel_visible=%d\n", visible);

    const char *names[] = {"mnt", "pid", "user", "net", "ipc", "uts"};
    for (size_t i = 0; i < sizeof names / sizeof names[0]; i++) {
        char path[64];
        char target[64];
        snprintf(path, sizeof path, "/proc/self/ns/%s", names[i]);
        ssize_t length = readlink(path, target, sizeof target - 1);
        if (length < 0)
            return 2;
        target[length] = '\0';
        printf("ns_%s=%s\n", names[i], target);
    }
    printf("uid=%ld\n", (long)getuid());
    FILE *status = fopen("/proc/self/status", "r");
    if (!status)
        return 2;
    const char *fields[] = {"CapEff:", "NoNewPrivs:", "Seccomp_filters:"};
    char line[256];
    while (fgets(line, sizeof line, status)) {
        for (size_t i = 0; i < sizeof fields / sizeof fields[0]; i++) {
            size_t field_size = strlen(fields[i]);
            if (strncmp(line, fields[i], field_size) == 0) {
                char *value = line + field_size;
                value += strspn(value, " \t");
                printf("%.*s=%s", (int)field_size - 1, fields[i], value);
            }
        }
    }
    fclose(status);
    return 0;
}

static void inspect_network(int port)
{
    char target[64];
    ssize_t length = readlink("/proc/self/ns/net", target, sizeof target - 1);
    if (length >= 0) {
        target[length] = '\0';
        printf("net_ns=%s\n", target);
    }
    struct sockaddr_in address = {
        .sin_family = AF_INET,
        .sin_port = htons(port),
        .sin_addr = {.s_addr = htonl(INADDR_LOOPBACK)}
    };
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    printf("socket_errno=%d\n", fd < 0 ? errno : 0);
    if (fd >= 0) {
        struct timeval timeout = {.tv_sec = 1};
        if (setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout) < 0) {
            printf("socket_setup_errno=%d\n", errno);
        } else {
            int status = connect(fd, (struct sockaddr *)&address, sizeof address);
            printf("connect_errno=%d\n", status < 0 ? errno : 0);
        }
        close(fd);
    }
    fd = socket(AF_INET6, SOCK_STREAM, 0);
    printf("ipv6_socket_errno=%d\n", fd < 0 ? errno : 0);
    if (fd >= 0)
        close(fd);
    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    printf("unix_socket_errno=%d\n", fd < 0 ? errno : 0);
    if (fd >= 0)
        close(fd);
}

static int inspect_tasks(void)
{
    pid_t children[24];
    size_t count = 0;
    int fork_errno = 0;
    for (; count < sizeof children / sizeof children[0]; count++) {
        pid_t child = fork();
        if (child < 0) {
            fork_errno = errno;
            break;
        }
        if (child == 0) {
            sleep(4);
            _exit(0);
        }
        children[count] = child;
    }
    printf("children=%zu\nfork_errno=%d\n", count, fork_errno);
    for (size_t i = 0; i < count; i++)
        kill(children[i], SIGTERM);
    for (size_t i = 0; i < count; i++) {
        while (waitpid(children[i], NULL, 0) < 0 && errno == EINTR)
            continue;
    }
    return 0;
}

static int inspect_memory(int mib)
{
    size_t size = (size_t)mib * 1024 * 1024;
    volatile unsigned char *buffer = malloc(size);
    if (!buffer) {
        printf("malloc_errno=%d\n", errno);
        return 2;
    }
    long page = sysconf(_SC_PAGESIZE);
    if (page <= 0) {
        free((void *)buffer);
        return 2;
    }
    for (size_t offset = 0; offset < size; offset += (size_t)page)
        buffer[offset] = 1;
    printf("touched_mib=%d\n", mib);
    free((void *)buffer);
    return 0;
}

static long long microseconds(clockid_t clock)
{
    struct timespec sample;
    if (clock_gettime(clock, &sample) < 0)
        exit(2);
    return (long long)sample.tv_sec * 1000000 + sample.tv_nsec / 1000;
}

static void inspect_cpu(void)
{
    long long started = microseconds(CLOCK_MONOTONIC);
    long long cpu_started = microseconds(CLOCK_PROCESS_CPUTIME_ID);
    long long elapsed;
    do {
        elapsed = microseconds(CLOCK_MONOTONIC) - started;
    } while (elapsed < 1200000);
    printf("wall_us=%lld\ncpu_us=%lld\n", elapsed,
           microseconds(CLOCK_PROCESS_CPUTIME_ID) - cpu_started);
}

int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IOLBF, 0);
    if (argc >= 3 && strcmp(argv[1], "resource") == 0) {
        FILE *groups = fopen("/proc/self/cgroup", "r");
        if (groups) {
            char line[PATH_MAX];
            while (fgets(line, sizeof line, groups)) {
                if (strncmp(line, "0::", 3) == 0)
                    printf("lab_group=%s", line + 3);
            }
            fclose(groups);
        }
        puts("payload_started=1");
        struct timespec ready_delay = {.tv_nsec = 300000000};
        nanosleep(&ready_delay, NULL);
        ++argv;
        --argc;
    }
    if (argc == 2 && strcmp(argv[1], "hello") == 0) {
        puts("hello=1");
    } else if (argc == 3 && strcmp(argv[1], "sentinel") == 0) {
        if (prctl(PR_SET_NAME, argv[2], 0, 0, 0) < 0)
            return 2;
        puts("ready");
        pause();
    } else if (argc == 5 && strcmp(argv[1], "files") == 0) {
        inspect_files(argv[2], argv[3], argv[4]);
    } else if (argc == 3 && strcmp(argv[1], "pid") == 0) {
        return inspect_processes(argv[2]);
    } else if (argc == 3 && strcmp(argv[1], "net") == 0) {
        inspect_network(atoi(argv[2]));
    } else if (argc == 2 && strcmp(argv[1], "tasks") == 0) {
        return inspect_tasks();
    } else if (argc == 3 && strcmp(argv[1], "memory") == 0) {
        int mib = atoi(argv[2]);
        if (mib != 16 && mib != 128)
            return 2;
        return inspect_memory(mib);
    } else if (argc == 2 && strcmp(argv[1], "cpu") == 0) {
        inspect_cpu();
    } else {
        return 2;
    }
    return 0;
}
