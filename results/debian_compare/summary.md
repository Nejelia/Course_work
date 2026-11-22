# Результаты сравнительного исследования

## Серия functional

Debian GNU/Linux 13 (trixie), ядро 6.18.57, x86_64, CPU 9. bubblewrap 0.12.0, —.

Диагностический запуск с общей сетью.

- bubblewrap: PASS 21, FAIL 0, UNAVAILABLE 0.
- host: PASS 15, FAIL 0, UNAVAILABLE 0.

| Среда | Режим | Тест | Статус | Первый повтор |
| --- | --- | --- | --- | --- |
| host | shared | hello | PASS |  |
| host | shared | files | PASS | `hidden_errno=0`, `input_read=1`, `input_write_errno=0`, `scratch_errno=0` |
| host | shared | pid | PASS | `sentinel_visible=1`, `ns_pid=pid:[4026532384]`, `NoNewPrivs=1` |
| host | shared | net | PASS | `net_ns=net:[4026532385]`, `socket_errno=0`, `connect_errno=0`, `ipv6_socket_errno=0` |
| host | shared | csv | PASS | `books=120` и `services=75` |
| bubblewrap | shared | hello | PASS |  |
| bubblewrap | shared | files | PASS | `hidden_errno=ENOENT`, `input_read=1`, `input_write_errno=EROFS`, `scratch_errno=0` |
| bubblewrap | shared | pid | PASS | `sentinel_visible=0`, `ns_pid=pid:[4026532324]`, `NoNewPrivs=1` |
| bubblewrap | shared | net | PASS | `net_ns=net:[4026532385]`, `socket_errno=0`, `connect_errno=0`, `ipv6_socket_errno=0` |
| bubblewrap | shared | csv | PASS | `books=120` и `services=75` |
| bubblewrap | filter | net | PASS | `net_ns=net:[4026532385]`, `socket_errno=EPERM`, `connect_errno=—`, `ipv6_socket_errno=EPERM` |
| bubblewrap | shared | csv_missing | PASS | `FileNotFoundError` |

## Серия timing

Debian GNU/Linux 13 (trixie), ядро 6.18.57, x86_64, CPU 9. bubblewrap 0.12.0, —.

Диагностический запуск с общей сетью.

- bubblewrap: PASS 14, FAIL 0, UNAVAILABLE 0.
- host: PASS 14, FAIL 0, UNAVAILABLE 0.

Два прогревочных запуска пропущены. Таблица учитывает успешные измерения.

| Среда | Нагрузка | Успехов / запусков | Медиана мс | Q1–Q3 мс |
| --- | --- | --- | --- | --- |
| bubblewrap | csv | 5/5 | 52.37 | 50.07–54.67 |
| bubblewrap | hello | 5/5 | 2.48 | 2.31–2.68 |
| host | csv | 5/5 | 13.47 | 13.30–14.62 |
| host | hello | 5/5 | 0.62 | 0.60–0.63 |

