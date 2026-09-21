# Local-production start/stop window

Portfolio IA runs locally (see `docker-compose.yml`) instead of on Azure. Two Windows
Scheduled Tasks keep it up automatically during the hours it's actually used, instead
of running 24/7 or needing someone to start it by hand:

| Task                  | Trigger (Europe/Madrid) | Runs                          |
|------------------------|--------------------------|--------------------------------|
| `PortfolioIA - Start`  | Daily 13:00              | `scripts/docker-window-start.ps1` — launches Docker Desktop if needed, then `docker compose up -d` |
| `PortfolioIA - Stop`   | Daily 19:00              | `scripts/docker-window-stop.ps1` — `docker compose stop` (containers only; Docker Desktop itself stays running) |

Registered once via `Register-ScheduledTask` (PowerShell), tied to the current Windows
user, `-StartWhenAvailable` so a missed 13:00 (machine asleep/off) still runs as soon
as the machine is next available.

**Known gap:** if the machine reboots *during* the 13:00–19:00 window, nothing brings
the stack back up until the next 13:00 trigger — there's no "on login, if within the
window, start" safeguard yet. Ask if you want that added (a third task with an
`AtLogOn` trigger that checks the current time before acting).

**Docker Desktop's own "Start Docker Desktop when you sign in" setting is deliberately
left OFF** — turning it on would launch Docker at every login regardless of the
13:00–19:00 window, defeating the point of scheduling it.

## Managing the tasks

```powershell
Get-ScheduledTask -TaskName "PortfolioIA*"
Get-ScheduledTaskInfo -TaskName "PortfolioIA - Start"   # next/last run
Start-ScheduledTask -TaskName "PortfolioIA - Start"     # run now, manually
Disable-ScheduledTask -TaskName "PortfolioIA - Start", "PortfolioIA - Stop"   # pause both
Unregister-ScheduledTask -TaskName "PortfolioIA - Start", "PortfolioIA - Stop" -Confirm:$false   # remove
```

To change the window, edit the trigger time on each task (`Set-ScheduledTask` with a
new `-Trigger`) rather than editing the `.ps1` files, which don't hardcode any time.
