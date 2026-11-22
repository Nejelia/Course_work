# Результаты сравнительного исследования

## Серия check

Ubuntu 24.04.5 LTS, ядро 7.0.0-38-generic, x86_64, CPU 4. bubblewrap 0.9.0, podman version 4.9.3.

- bubblewrap: PASS 3, FAIL 0, UNAVAILABLE 0.
- podman: PASS 3, FAIL 0, UNAVAILABLE 0.


## Серия functional

Ubuntu 24.04.5 LTS, ядро 7.0.0-38-generic, x86_64, CPU 4. bubblewrap 0.9.0, podman version 4.9.3.

- bubblewrap: PASS 45, FAIL 0, UNAVAILABLE 0.
- host: PASS 25, FAIL 0, UNAVAILABLE 0.
- podman: PASS 45, FAIL 0, UNAVAILABLE 0.

| Среда | Режим | Тест | Статус | Первый повтор |
| --- | --- | --- | --- | --- |
| host | shared | hello | PASS |  |
| host | shared | files | PASS | `hidden_errno=0`, `input_read=1`, `input_write_errno=0`, `scratch_errno=0` |
| host | shared | pid | PASS | `sentinel_visible=1`, `ns_pid=pid:[4026531836]`, `NoNewPrivs=0` |
| host | shared | net | PASS | `net_ns=net:[4026531833]`, `socket_errno=0`, `connect_errno=0`, `ipv6_socket_errno=0` |
| host | shared | csv | PASS | `books=120` и `services=75` |
| bubblewrap | shared | net | PASS | `net_ns=net:[4026531833]`, `socket_errno=0`, `connect_errno=0`, `ipv6_socket_errno=0` |
| bubblewrap | net | net | PASS | `net_ns=net:[4026532853]`, `socket_errno=0`, `connect_errno=ECONNREFUSED`, `ipv6_socket_errno=0` |
| bubblewrap | filter | net | PASS | `net_ns=net:[4026531833]`, `socket_errno=EPERM`, `connect_errno=—`, `ipv6_socket_errno=EPERM` |
| bubblewrap | full | net | PASS | `net_ns=net:[4026532968]`, `socket_errno=EPERM`, `connect_errno=—`, `ipv6_socket_errno=EPERM` |
| bubblewrap | full | hello | PASS |  |
| bubblewrap | full | files | PASS | `hidden_errno=ENOENT`, `input_read=1`, `input_write_errno=EROFS`, `scratch_errno=0` |
| bubblewrap | full | pid | PASS | `sentinel_visible=0`, `ns_pid=pid:[4026532852]`, `NoNewPrivs=1` |
| bubblewrap | full | csv | PASS | `books=120` и `services=75` |
| bubblewrap | full | csv_missing | PASS | `FileNotFoundError` |
| podman | shared | net | PASS | `net_ns=net:[4026531833]`, `socket_errno=0`, `connect_errno=0`, `ipv6_socket_errno=0` |
| podman | net | net | PASS | `net_ns=net:[4026532848]`, `socket_errno=0`, `connect_errno=ECONNREFUSED`, `ipv6_socket_errno=0` |
| podman | filter | net | PASS | `net_ns=net:[4026531833]`, `socket_errno=EPERM`, `connect_errno=—`, `ipv6_socket_errno=EPERM` |
| podman | full | net | PASS | `net_ns=net:[4026532848]`, `socket_errno=EPERM`, `connect_errno=—`, `ipv6_socket_errno=EPERM` |
| podman | full | hello | PASS |  |
| podman | full | files | PASS | `hidden_errno=ENOENT`, `input_read=1`, `input_write_errno=EROFS`, `scratch_errno=0` |
| podman | full | pid | PASS | `sentinel_visible=0`, `ns_pid=pid:[4026532847]`, `NoNewPrivs=1` |
| podman | full | csv | PASS | `books=120` и `services=75` |
| podman | full | csv_missing | PASS | `FileNotFoundError` |

## Серия resources

Ubuntu 24.04.5 LTS, ядро 7.0.0-38-generic, x86_64, CPU 4. bubblewrap 0.9.0, podman version 4.9.3.

- bubblewrap: PASS 27, FAIL 0, UNAVAILABLE 0.
- podman: PASS 27, FAIL 0, UNAVAILABLE 0.

Δ счётчика относится к oom_kill, pids.events:max или nr_throttled соответственно. Пик относится ко всей группе.

| Среда | Повтор | Тест | Лимиты | Статус | Исход | Δ счётчика | Пик МиБ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bubblewrap | 1 | memory | 64 МиБ / 64 задач / 100% | PASS | OOM | 1 | 64.0 |
| podman | 1 | memory | 64 МиБ / 64 задач / 100% | PASS | OOM | 1 | 64.0 |
| bubblewrap | 1 | memory | 128 МиБ / 64 задач / 100% | PASS | OOM | 1 | 128.0 |
| podman | 1 | memory | 128 МиБ / 64 задач / 100% | PASS | OOM | 1 | 128.0 |
| bubblewrap | 1 | memory | 256 МиБ / 64 задач / 100% | PASS | 128 MiB | 0 | 138.54 |
| podman | 1 | memory | 256 МиБ / 64 задач / 100% | PASS | 128 MiB | 0 | 147.6 |
| bubblewrap | 1 | tasks | 256 МиБ / 16 задач / 100% | PASS | 12 | 1 | — |
| podman | 1 | tasks | 256 МиБ / 16 задач / 100% | PASS | 5 | 21 | — |
| bubblewrap | 1 | tasks | 256 МиБ / 24 задач / 100% | PASS | 20 | 1 | — |
| podman | 1 | tasks | 256 МиБ / 24 задач / 100% | PASS | 13 | 1 | — |
| bubblewrap | 1 | tasks | 256 МиБ / 64 задач / 100% | PASS | 24 | 0 | — |
| podman | 1 | tasks | 256 МиБ / 64 задач / 100% | PASS | 24 | 0 | — |
| bubblewrap | 1 | cpu | 256 МиБ / 64 задач / 25% | PASS | 0.2573 | 13 | — |
| podman | 1 | cpu | 256 МиБ / 64 задач / 25% | PASS | 0.2647 | 24 | — |
| bubblewrap | 1 | cpu | 256 МиБ / 64 задач / 50% | PASS | 0.3974 | 8 | — |
| podman | 1 | cpu | 256 МиБ / 64 задач / 50% | PASS | 0.3782 | 15 | — |
| bubblewrap | 1 | cpu | 256 МиБ / 64 задач / 100% | PASS | 0.8312 | 13 | — |
| podman | 1 | cpu | 256 МиБ / 64 задач / 100% | PASS | 0.9938 | 6 | — |
| bubblewrap | 2 | memory | 64 МиБ / 64 задач / 100% | PASS | OOM | 1 | 64.0 |
| podman | 2 | memory | 64 МиБ / 64 задач / 100% | PASS | OOM | 1 | 64.0 |
| bubblewrap | 2 | memory | 128 МиБ / 64 задач / 100% | PASS | OOM | 1 | 128.0 |
| podman | 2 | memory | 128 МиБ / 64 задач / 100% | PASS | OOM | 1 | 128.0 |
| bubblewrap | 2 | memory | 256 МиБ / 64 задач / 100% | PASS | 128 MiB | 0 | 138.29 |
| podman | 2 | memory | 256 МиБ / 64 задач / 100% | PASS | 128 MiB | 0 | 147.91 |
| bubblewrap | 2 | tasks | 256 МиБ / 16 задач / 100% | PASS | 12 | 1 | — |
| podman | 2 | tasks | 256 МиБ / 16 задач / 100% | PASS | 4 | 21 | — |
| bubblewrap | 2 | tasks | 256 МиБ / 24 задач / 100% | PASS | 20 | 1 | — |
| podman | 2 | tasks | 256 МиБ / 24 задач / 100% | PASS | 13 | 1 | — |
| bubblewrap | 2 | tasks | 256 МиБ / 64 задач / 100% | PASS | 24 | 0 | — |
| podman | 2 | tasks | 256 МиБ / 64 задач / 100% | PASS | 24 | 0 | — |
| bubblewrap | 2 | cpu | 256 МиБ / 64 задач / 25% | PASS | 0.2622 | 13 | — |
| podman | 2 | cpu | 256 МиБ / 64 задач / 25% | PASS | 0.2481 | 21 | — |
| bubblewrap | 2 | cpu | 256 МиБ / 64 задач / 50% | PASS | 0.416 | 9 | — |
| podman | 2 | cpu | 256 МиБ / 64 задач / 50% | PASS | 0.4032 | 19 | — |
| bubblewrap | 2 | cpu | 256 МиБ / 64 задач / 100% | PASS | 0.9979 | 0 | — |
| podman | 2 | cpu | 256 МиБ / 64 задач / 100% | PASS | 0.9965 | 6 | — |
| bubblewrap | 3 | memory | 64 МиБ / 64 задач / 100% | PASS | OOM | 1 | 64.0 |
| podman | 3 | memory | 64 МиБ / 64 задач / 100% | PASS | OOM | 1 | 64.0 |
| bubblewrap | 3 | memory | 128 МиБ / 64 задач / 100% | PASS | OOM | 1 | 128.0 |
| podman | 3 | memory | 128 МиБ / 64 задач / 100% | PASS | OOM | 1 | 128.0 |
| bubblewrap | 3 | memory | 256 МиБ / 64 задач / 100% | PASS | 128 MiB | 0 | 138.33 |
| podman | 3 | memory | 256 МиБ / 64 задач / 100% | PASS | 128 MiB | 0 | 148.22 |
| bubblewrap | 3 | tasks | 256 МиБ / 16 задач / 100% | PASS | 12 | 1 | — |
| podman | 3 | tasks | 256 МиБ / 16 задач / 100% | PASS | 4 | 21 | — |
| bubblewrap | 3 | tasks | 256 МиБ / 24 задач / 100% | PASS | 20 | 1 | — |
| podman | 3 | tasks | 256 МиБ / 24 задач / 100% | PASS | 12 | 1 | — |
| bubblewrap | 3 | tasks | 256 МиБ / 64 задач / 100% | PASS | 24 | 0 | — |
| podman | 3 | tasks | 256 МиБ / 64 задач / 100% | PASS | 24 | 0 | — |
| bubblewrap | 3 | cpu | 256 МиБ / 64 задач / 25% | PASS | 0.2684 | 12 | — |
| podman | 3 | cpu | 256 МиБ / 64 задач / 25% | PASS | 0.2515 | 22 | — |
| bubblewrap | 3 | cpu | 256 МиБ / 64 задач / 50% | PASS | 0.5165 | 12 | — |
| podman | 3 | cpu | 256 МиБ / 64 задач / 50% | PASS | 0.4998 | 17 | — |
| bubblewrap | 3 | cpu | 256 МиБ / 64 задач / 100% | PASS | 1.0 | 0 | — |
| podman | 3 | cpu | 256 МиБ / 64 задач / 100% | PASS | 0.994 | 6 | — |

## Серия timing

Ubuntu 24.04.5 LTS, ядро 7.0.0-38-generic, x86_64, CPU 4. bubblewrap 0.9.0, podman version 4.9.3.

- bubblewrap: PASS 64, FAIL 0, UNAVAILABLE 0.
- host: PASS 64, FAIL 0, UNAVAILABLE 0.
- podman: PASS 64, FAIL 0, UNAVAILABLE 0.

Два прогревочных запуска пропущены. Таблица учитывает успешные измерения.

| Среда | Нагрузка | Успехов / запусков | Медиана мс | Q1–Q3 мс |
| --- | --- | --- | --- | --- |
| bubblewrap | csv | 30/30 | 74.75 | 73.56–76.68 |
| bubblewrap | hello | 30/30 | 7.29 | 7.13–7.75 |
| host | csv | 30/30 | 19.06 | 18.12–20.07 |
| host | hello | 30/30 | 1.65 | 1.44–1.96 |
| podman | csv | 30/30 | 298.05 | 293.21–302.36 |
| podman | hello | 30/30 | 229.58 | 225.68–233.87 |

