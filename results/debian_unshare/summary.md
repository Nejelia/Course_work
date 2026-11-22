# Результаты эксперимента

- Окружение: Debian GNU/Linux 13 (trixie), ядро 6.18.57, bubblewrap 0.12.0.
- Сеть: `unshare`. Число повторов: 5.

| Профиль | PASS | FAIL | UNAVAILABLE |
|---|---:|---:|---:|
| P0 | 20 | 0 | 0 |
| P1 | 20 | 0 | 0 |
| P2 | 20 | 0 | 0 |
| P3 | 40 | 0 | 0 |
| P4 | 40 | 0 | 0 |

## Файлы процессы и сеть

Наблюдения первого повтора. Прочерк обозначает отсутствие значения в журнале.

| Профиль | Тест | Статус | Наблюдение |
|---|---|---|---|
| P0 | files | PASS | `hidden_errno=0`, `input_read=1`, `input_write_errno=0`, `scratch_errno=0` |
| P0 | pid | PASS | `sentinel_visible=1`, `ns_pid=pid:[4026532387]`, `ns_net=net:[4026532388]`, `Seccomp_filters=1` |
| P0 | net | PASS | `socket_errno=0`, `connect_errno=0`, `ipv6_socket_errno=0`, `unix_socket_errno=EPERM` |
| P1 | files | PASS | `hidden_errno=ENOENT`, `input_read=1`, `input_write_errno=EROFS`, `scratch_errno=0` |
| P1 | pid | PASS | `sentinel_visible=0`, `ns_pid=pid:[4026532320]`, `ns_net=net:[4026532388]`, `Seccomp_filters=1` |
| P1 | net | PASS | `socket_errno=0`, `connect_errno=0`, `ipv6_socket_errno=0`, `unix_socket_errno=EPERM` |
| P2 | files | PASS | `hidden_errno=ENOENT`, `input_read=1`, `input_write_errno=EROFS`, `scratch_errno=0` |
| P2 | pid | PASS | `sentinel_visible=0`, `ns_pid=pid:[4026532457]`, `ns_net=net:[4026532322]`, `Seccomp_filters=1` |
| P2 | net | PASS | `socket_errno=0`, `connect_errno=ENETUNREACH`, `ipv6_socket_errno=0`, `unix_socket_errno=EPERM` |
| P3 | files | PASS | `hidden_errno=ENOENT`, `input_read=1`, `input_write_errno=EROFS`, `scratch_errno=0` |
| P3 | pid | PASS | `sentinel_visible=0`, `ns_pid=pid:[4026532321]`, `ns_net=net:[4026532388]`, `Seccomp_filters=2` |
| P3 | net | PASS | `socket_errno=EPERM`, `ipv6_socket_errno=EPERM`, `unix_socket_errno=EPERM` |
| P4 | files | PASS | `hidden_errno=ENOENT`, `input_read=1`, `input_write_errno=EROFS`, `scratch_errno=0` |
| P4 | pid | PASS | `sentinel_visible=0`, `ns_pid=pid:[4026532522]`, `ns_net=net:[4026532319]`, `Seccomp_filters=2` |
| P4 | net | PASS | `socket_errno=EPERM`, `ipv6_socket_errno=EPERM`, `unix_socket_errno=EPERM` |

## Ресурсы

Δ обозначает разность между показаниями после и до теста. Прочерк означает отсутствие измерения, в том числе в профиле без квот.

| Профиль | Повтор | Тест | Статус | Наблюдение | Δ счётчика |
|---|---:|---|---|---|---|
| P3 | 1 | tasks | PASS | children=24, fork=0 | — |
| P3 | 1 | memory16 | PASS | МиБ=16, код=0 | — |
| P3 | 1 | memory128 | PASS | МиБ=128, код=0 | — |
| P3 | 1 | cpu | PASS | CPU / wall = 0.9996 | — |
| P4 | 1 | tasks | PASS | children=24, fork=0 | — |
| P4 | 1 | memory16 | PASS | МиБ=16, код=0 | — |
| P4 | 1 | memory128 | PASS | МиБ=128, код=0 | — |
| P4 | 1 | cpu | PASS | CPU / wall = 0.998 | — |
| P3 | 2 | tasks | PASS | children=24, fork=0 | — |
| P3 | 2 | memory16 | PASS | МиБ=16, код=0 | — |
| P3 | 2 | memory128 | PASS | МиБ=128, код=0 | — |
| P3 | 2 | cpu | PASS | CPU / wall = 0.9996 | — |
| P4 | 2 | tasks | PASS | children=24, fork=0 | — |
| P4 | 2 | memory16 | PASS | МиБ=16, код=0 | — |
| P4 | 2 | memory128 | PASS | МиБ=128, код=0 | — |
| P4 | 2 | cpu | PASS | CPU / wall = 0.9988 | — |
| P3 | 3 | tasks | PASS | children=24, fork=0 | — |
| P3 | 3 | memory16 | PASS | МиБ=16, код=0 | — |
| P3 | 3 | memory128 | PASS | МиБ=128, код=0 | — |
| P3 | 3 | cpu | PASS | CPU / wall = 0.9993 | — |
| P4 | 3 | tasks | PASS | children=24, fork=0 | — |
| P4 | 3 | memory16 | PASS | МиБ=16, код=0 | — |
| P4 | 3 | memory128 | PASS | МиБ=128, код=0 | — |
| P4 | 3 | cpu | PASS | CPU / wall = 0.9989 | — |
| P3 | 4 | tasks | PASS | children=24, fork=0 | — |
| P3 | 4 | memory16 | PASS | МиБ=16, код=0 | — |
| P3 | 4 | memory128 | PASS | МиБ=128, код=0 | — |
| P3 | 4 | cpu | PASS | CPU / wall = 0.9895 | — |
| P4 | 4 | tasks | PASS | children=24, fork=0 | — |
| P4 | 4 | memory16 | PASS | МиБ=16, код=0 | — |
| P4 | 4 | memory128 | PASS | МиБ=128, код=0 | — |
| P4 | 4 | cpu | PASS | CPU / wall = 0.9945 | — |
| P3 | 5 | tasks | PASS | children=24, fork=0 | — |
| P3 | 5 | memory16 | PASS | МиБ=16, код=0 | — |
| P3 | 5 | memory128 | PASS | МиБ=128, код=0 | — |
| P3 | 5 | cpu | PASS | CPU / wall = 0.998 | — |
| P4 | 5 | tasks | PASS | children=24, fork=0 | — |
| P4 | 5 | memory16 | PASS | МиБ=16, код=0 | — |
| P4 | 5 | memory128 | PASS | МиБ=128, код=0 | — |
| P4 | 5 | cpu | PASS | CPU / wall = 0.9987 | — |

## Доля процессорного времени

- P3: n = 5, медиана 0.999, минимум 0.990, максимум 1.000.
- P4: n = 5, медиана 0.999, минимум 0.995, максимум 0.999.
