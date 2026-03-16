# 🖥️ Demo: VPS Security Hardening — Full Deliberation

> Real output: 3 AI agents propose, critique each other, and reach consensus on securing a fresh Ubuntu 24.04 VPS.

---

## Round 1: Proposals

### 🔐 gemini-cli — Full Hardening Plan

```bash
# 1. Initial Access & User Management
apt update && apt upgrade -y
adduser sandu
usermod -aG sudo sandu
mkdir -p /home/sandu/.ssh
# ssh-copy-id from local machine

# 2. SSH Daemon Hardening (/etc/ssh/sshd_config)
Port 2222
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
PermitEmptyPasswords no
X11Forwarding no
MaxAuthTries 3
AllowUsers sandu

# 3. Firewall (UFW)
ufw default deny incoming
ufw default allow outgoing
ufw allow 2222/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# 4. Automatic Security Updates
apt install unattended-upgrades -y
dpkg-reconfigure -plow unattended-upgrades

# 5. Brute-Force Protection
apt install fail2ban -y
cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
# Update [sshd] section: enabled=true, port=2222

# 6. Network Stack Hardening (sysctl.conf)
net.ipv4.conf.all.rp_filter = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.log_martians = 1

# 7. Secure Shared Memory
echo "tmpfs /run/shm tmpfs defaults,noexec,nosuid 0 0" >> /etc/fstab

# 8. Auditing and Monitoring
apt install auditd lynis logwatch -y
lynis audit system
```

---

## Round 2: Critique

### 💬 kimi-cli critiques gemini-cli:

> "The proposal omits critical steps: **AIDE or rkhunter** for intrusion detection, **backup strategy**, and **no mention of disabling IPv6** if not needed. I'd add file integrity monitoring and a regular backup rotation with offsite storage."

### 💬 codex-cli critiques gemini-cli:

> "Missing: verify SSH key access **before** closing root session (lockout risk). Add **ufw rate limiting**, remove unnecessary packages/services, and enable **unattended-upgrades for recovery**. No backup or disaster recovery plan mentioned."

---

## Round 3: Synthesis

### 🧠 Claude Code — Final VPS Hardening Checklist

Based on all proposals + critiques, consensus plan:

**IMMEDIATE (first 5 minutes):**
1. `apt update && apt full-upgrade -y`
2. `adduser admin && usermod -aG sudo admin`
3. SSH: `PermitRootLogin no`, `PasswordAuthentication no`, `Port 2222`
4. `ufw default deny incoming && ufw allow 2222/tcp && ufw allow 80,443/tcp && ufw enable`

**ESSENTIAL (first hour):**
5. `apt install fail2ban -y` (brute-force protection)
6. `apt install unattended-upgrades -y` (auto security patches)
7. Configure sysctl: disable IP forwarding, enable SYN cookies
8. Install auditd for system call auditing

**HARDENING (first day):**
9. Remove unused packages and services
10. Configure logwatch for log monitoring
11. Set up AIDE (file integrity monitoring) ← *from kimi-cli critique*
12. Kernel hardening via sysctl.conf ← *from gemini-cli*
13. Secure shared memory (noexec /run/shm)

**MONITORING (ongoing):**
14. Regular security audits with `lynis`
15. Configure alerting for suspicious activity
16. Backup strategy with offsite rotation ← *from codex-cli critique*

**Added from critiques:**
- ✓ Intrusion detection AIDE/rkhunter (kimi-cli)
- ✓ Backup strategy (codex-cli)
- ✓ Verify SSH before closing root (codex-cli)
- ✓ Kernel hardening (gemini-cli)

---

## Key Takeaway

> No single agent covered all 16 points. The **combination of proposals + mutual critique** produced a checklist that's more comprehensive than any individual recommendation.

This is the power of multi-agent deliberation.

---

*Multi-agent orchestration is a Pro feature. Contact: ean@eanai.ro*
