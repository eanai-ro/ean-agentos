# 🖥️ Demo: VPS Security Hardening — Full Deliberation

> Real output: 3 AI agents propose, critique each other, and reach consensus on securing a fresh Ubuntu 24.04 VPS.

---

## Round 1: Proposals

### 🔐 gemini-cli — 8-Step Hardening Plan

```
1. User Management: adduser + sudo, SSH key auth
2. SSH Hardening: Port 2222, PermitRootLogin no, PasswordAuthentication no,
   PubkeyAuthentication yes, MaxAuthTries 3, AllowUsers sandu
3. Firewall (UFW): default deny incoming, allow 2222/80/443
4. Auto Updates: unattended-upgrades for security patches
5. Fail2Ban: SSH brute-force protection on port 2222
6. Kernel Hardening (sysctl): rp_filter, SYN cookies, log martians,
   disable source routing, ignore ICMP broadcasts
7. Secure Shared Memory: noexec,nosuid on /run/shm
8. Auditing: auditd + lynis + logwatch
```

### 🔐 kimi-cli — Automated Hardening Script

```
Created a 27KB automated hardening script covering:

1. Authentication: root disabled, SSH keys only, account lockout after
   5 failed attempts, 14+ char password policy
2. SSH: modern crypto algorithms, 3 auth tries max, 5 min idle timeout,
   TCP/X11 forwarding disabled, legal banner
3. Firewall (UFW): default deny, SSH with rate limiting, IPv6 support
4. Fail2ban: SSH protection + recidive filter for repeat offenders
5. Kernel: ASLR enabled, core dumps disabled, protected hardlinks/symlinks,
   SYN cookies, reverse path filtering
6. File Integrity: AIDE with daily automated scans + email alerts
7. Rootkit Detection: rkhunter + chkrootkit daily scans
8. AppArmor profiles enforced
```

### 🔐 codex-cli — Operational Runbook

```
Pre-flight: provider snapshot + out-of-band console access
Keep root SSH open until new user verified!

1. Immediate updates: hostnamectl, timedatectl UTC, apt full-upgrade
   Install: ufw fail2ban unattended-upgrades apparmor auditd aide
2. Admin user: adduser + sudo + sshadmins group, SSH key setup
3. SSH hardening: AllowGroups sshadmins, MaxAuthTries 3,
   LoginGraceTime 30, ClientAliveInterval 300
4. Firewall: ufw default deny, allow admin IP for SSH,
   rate limit: ufw limit ssh/tcp
5. Fail2ban: custom jail.local, progressive ban times
6. Unattended-upgrades: security only, auto-reboot at 4AM if needed
7. AppArmor: enforce all profiles
8. Auditd: monitor /etc/passwd, /etc/shadow, sudoers changes
9. AIDE: initialize database, daily cron checks
```

---

## Round 2: Mutual Critique

### 💬 kimi-cli critiques gemini + codex:

> "Gemini's plan is solid but missing **intrusion detection** (AIDE/rkhunter), **backup strategy**, and **AppArmor** enforcement. Codex has the right idea with pre-flight safety but doesn't mention **kernel hardening** (sysctl) or **shared memory** protection."

### 💬 codex-cli critiques gemini + kimi:

> "Both miss the critical step: **verify SSH key access in a new terminal BEFORE closing root**. Gemini should add **UFW rate limiting** (not just allow). Kimi's automated script is convenient but risky — one wrong step and you're locked out. Always test manually first."

### 💬 gemini-cli critiques kimi + codex:

> "Kimi's automated approach is efficient but lacks **manual verification steps**. Codex's runbook is thorough but should include **sysctl kernel hardening** and **shared memory restrictions**. Neither mentions **logwatch** for daily log summaries."

---

## Round 3: Synthesis

### 🧠 Claude Code — Final 16-Point VPS Hardening Checklist

Based on all 3 proposals + mutual critiques:

**IMMEDIATE (first 5 minutes):**
1. `apt update && apt full-upgrade -y`
2. `adduser admin && usermod -aG sudo admin`
3. SSH keys: copy public key, verify login in NEW terminal
4. SSH: `PermitRootLogin no`, `PasswordAuthentication no`, `Port 2222`
5. `ufw default deny incoming && ufw allow 2222/tcp && ufw enable`

**ESSENTIAL (first hour):**
6. `apt install fail2ban -y` + configure SSH jail
7. `apt install unattended-upgrades -y` (security patches only)
8. Kernel hardening via sysctl (SYN cookies, rp_filter, log martians)
9. Secure shared memory: noexec,nosuid on /run/shm

**HARDENING (first day):**
10. Install + configure auditd (monitor passwd, shadow, sudoers)
11. Install AIDE for file integrity monitoring ← *from kimi-cli*
12. Install rkhunter for rootkit detection ← *from kimi-cli*
13. Enforce AppArmor profiles ← *from codex-cli*
14. Install logwatch for daily log summaries ← *from gemini-cli*

**MONITORING (ongoing):**
15. Regular security audits with `lynis audit system`
16. Backup strategy with offsite rotation ← *from codex-cli critique*

**Key insight from critiques:**
- ✓ Always verify SSH in new terminal before closing root (codex-cli)
- ✓ Take provider snapshot before starting (codex-cli)
- ✓ Intrusion detection AIDE + rkhunter (kimi-cli)
- ✓ Kernel hardening sysctl (gemini-cli)
- ✓ AppArmor enforcement (kimi-cli + codex-cli)
- ✓ Logwatch for visibility (gemini-cli)

---

## Key Takeaway

> No single agent covered all 16 points. Gemini focused on **network hardening**, Kimi on **intrusion detection**, Codex on **operational safety**. The mutual critiques filled gaps that each agent missed.

This is the power of multi-agent deliberation with peer review.

---

*Multi-agent orchestration is a Pro feature. Contact: ean@eanai.ro*
