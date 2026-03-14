# Network and Host Security Training for OpenClaw Agent Systems

---

## Objective

Provide security guidance for running OpenClaw agent systems safely on:
- home networks
- isolated development machines
- small lab environments
- cloud infrastructure environments

The goal is to minimize attack surface without breaking OpenClaw functionality.

---

## Security Principles for Agent Systems

Agents should be treated as semi-trusted automation systems.

Key principles:
- least privilege
- network isolation
- credential containment
- audit logging
- controlled outbound access
- human approval for high-risk operations

Agents should never have unrestricted access to:
- home networks
- personal data
- administrator accounts
- full cloud control planes

---

## Local Machine Security

Supported host environments:
- macOS (Mac Mini)
- Windows workstation
- Linux workstation
- Linux servers

---

## Host Hardening Baseline

Every host running OpenClaw should implement:
- full disk encryption
- automatic security updates
- separate OS user account for agents
- firewall enabled
- minimal installed software
- remote access restricted

---

## Mac Mini Hardening

Recommended baseline:
- FileVault enabled
- macOS firewall enabled
- disable unnecessary sharing services
- create dedicated agent user account
- limit sudo access
- enable automatic updates

Example agent user: `openclaw-agent`

OpenClaw should run under this user instead of the main login account.

---

## Windows Machine Hardening

Recommended baseline:
- BitLocker enabled
- Windows Defender enabled
- Windows Firewall enabled
- disable SMB exposure outside LAN
- disable unnecessary services
- run OpenClaw under a dedicated user

Example user: `openclaw-agent`

---

## Linux Machine Hardening

Recommended baseline:
- full disk encryption
- automatic security patches
- UFW or iptables firewall
- disable root login over SSH
- SSH key authentication only
- separate service account

Example user: `openclaw-agent`

---

## File System Security

Sensitive files must never be stored inside the agent workspace.

Examples of sensitive data:
- API keys
- cloud credentials
- OAuth tokens
- private certificates

Secrets should instead be stored in:
- environment variables
- secure secret stores
- protected configuration directories

---

## Local Network Security

Agents should run on a segmented network.

Recommended home network layout:
- main network (personal devices)
- guest network (agent machines)
- IoT network (smart devices)

Agent systems should run on the **guest network**.

---

## Home Network Segmentation

```
router
├── main network
├── guest network      ← agent machines connect here
└── IoT network
```

Guest network restrictions:
- no access to main network devices
- no access to NAS storage
- no access to personal computers

---

## Local Firewall Rules

Host firewall should allow only required traffic.

Typical OpenClaw requirements:
- outbound HTTPS (443)
- local loopback connections
- internal messaging channels

Block:
- incoming connections from internet
- unnecessary open ports

---

## Outbound Traffic Control

Agents primarily need outbound access to:
- model providers
- API services
- source repositories

Outbound firewall rules should allow only necessary domains where possible.

---

## SSH Security

If remote access is required:
- disable password login
- use SSH keys only
- change default SSH port if exposed
- limit access by IP

---

## Logging and Audit

Every agent host should log:
- agent actions
- file modifications
- network activity
- system errors

Logs should be stored outside the agent workspace.

---

## Local Development Environment Safety

For development environments:
- agents should not run as administrator
- shell tool permissions should be restricted
- file system writes should be limited to project directories

---

## Container Sandboxing

Where possible, agents should run inside containers.

Example environments:
- Docker
- Podman
- Kubernetes

Container isolation limits filesystem and network access.

---

## Mac Mini Lab Deployment

Example secure setup:
- Mac Mini
- guest WiFi network
- OpenClaw running under agent user
- FileVault enabled
- firewall enabled
- Docker containers for agents

---

## Multi-Machine Home Lab

Example architecture:

```
Router
├── main network
└── guest network
    ├── Mac Mini (agent runtime)
    ├── Windows machine (testing)
    └── Linux VM (build runner)
```

All machines isolated from main network.

---

## Secrets Management

Secrets must never appear in:
- logs
- ticket files
- source repositories
- agent memory

Secrets should be stored using:
- environment variables
- cloud secret managers
- encrypted secret stores

---

## Secure Code Execution

Coding agents should never run arbitrary shell commands without validation.

Safe practices:
- allowlist safe commands
- block destructive commands
- require human approval for system modifications

---

## Network Security in Cloud Environments

When deploying OpenClaw agents in cloud infrastructure, use standard cloud security architecture.

---

## Microsoft Azure Deployment Security

Recommended architecture:
- Azure subscription
- virtual network (VNet)
- private subnets for agent VMs
- network security groups (NSG)

### Azure Network Layout

```
Virtual Network
├── public subnet
│   └── load balancer or gateway
└── private subnet
    └── OpenClaw agent VMs
```

Agent VMs should run in **private subnets only**.

### Network Security Group Rules

Inbound rules:
- allow SSH from admin IPs only
- deny all other inbound traffic

Outbound rules:
- allow HTTPS to model providers
- allow required API endpoints

### Azure Identity Management

Agents should authenticate using:
- Managed Identity
- Azure Key Vault

Avoid storing credentials directly on the VM.

### Azure Secret Management

Use Azure Key Vault for:
- API keys
- certificates
- database credentials

Agents retrieve secrets at runtime.

### VM Hardening in Azure

Agent VMs should use:
- latest OS images
- automatic security updates
- minimal installed packages
- restricted SSH access

### Azure Monitoring

Enable:
- Azure Monitor
- Defender for Cloud
- log analytics

---

## Multi-Agent Cloud Architecture

Example layout:

```
Azure VNet
├── agent coordinator VM
├── coding agent VM
└── testing agent VM
```

Each VM runs separate agent services.

---

## Zero Trust Networking

Agents should trust no network environment.
- All external input must be treated as untrusted
- Agents should not assume other agents are secure

---

## Protecting Against Lateral Movement

Machines should not be able to access each other unnecessarily.

Use firewall rules to prevent:
- VM to VM lateral access
- container breakout communication

---

## Secure Update Management

Hosts should enable automatic updates for:
- operating systems
- container images
- OpenClaw versions

---

## Security Testing for Agent Systems

Agents performing code review should check:
- [ ] network access permissions
- [ ] credential exposure
- [ ] unsafe shell execution
- [ ] open ports
- [ ] unrestricted file access
- [ ] insecure secret storage

---

## Incident Response Plan

If compromise is suspected:
1. disable agent tools
2. revoke credentials
3. rotate API keys
4. restore from clean backups
5. review logs

---

## Secure Deployment Summary

**Home deployment:**
- guest network isolation
- separate OS user
- host firewall enabled
- encrypted disk
- restricted outbound access

**Cloud deployment:**
- private subnets
- network security groups
- managed identities
- secure secret storage
- monitoring and logging
