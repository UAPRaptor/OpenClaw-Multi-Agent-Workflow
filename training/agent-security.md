# AI Agent Security Threats and Security Intelligence Sources
Training Material for Secure Agent Development and Code Review

---

## Primary Security Frameworks

OWASP GenAI Security Project
https://genai.owasp.org

OWASP Top 10 for Large Language Model Applications
https://owasp.org/www-project-top-10-for-large-language-model-applications/

OWASP Top 10 for Agentic Applications (2026)
https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/

OWASP AI Agent Security Cheat Sheet
https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html

These documents define the current industry baseline for securing AI agents and autonomous systems.

---

## Most Critical Agent Security Threats (2025–2026)

### Prompt Injection
Attackers insert malicious instructions into content that the agent processes. This can override system prompts and manipulate agent behavior.

**Direct Prompt Injection**
User-provided instructions override system rules.

**Indirect Prompt Injection**
Malicious instructions embedded in external data sources such as:
- web pages
- documents
- emails
- code repositories

Agents reading this content can unknowingly execute attacker instructions.

---

### Agent Goal Hijacking
Attackers manipulate the agent's objective.

Examples:
- changing task goals
- redirecting workflows
- forcing execution of unintended actions

Listed in the OWASP Agentic Top 10 as **Agent Goal Hijack**.

---

### Tool Misuse and Toolchain Abuse
Agents that have access to tools can be manipulated into using them incorrectly.

Examples:
- executing shell commands
- modifying repositories
- posting data to external APIs
- sending messages with sensitive information

Described in OWASP guidance as **Tool Abuse and Privilege Escalation**.

---

### Excessive Agent Permissions
If an agent has more permissions than necessary it can:
- read sensitive data
- modify files unexpectedly
- execute dangerous operations

OWASP calls this **Excessive Agency or Excessive Permissions**.

---

### Data Exfiltration
Agents may leak sensitive information through:
- tool outputs
- logs
- external API requests
- generated responses

Can expose: API keys, source code, credentials, private documents.

---

### Model and Data Poisoning
Training data or memory sources are intentionally manipulated to alter model behavior.

Examples:
- poisoned documentation
- malicious repository content
- adversarial datasets

OWASP identifies this as **Training Data Poisoning**.

---

### Agent Supply Chain Attacks
Agents depend on external components such as:
- plugins
- tools
- APIs
- model providers
- code libraries

Compromised dependencies can allow attackers to manipulate the agent.

OWASP calls this **Supply Chain Vulnerabilities**.

---

### Sensitive Information Disclosure
Agents can unintentionally expose sensitive data including:
- environment variables
- system prompts
- API tokens
- private repositories

Often occurs when agents output debug information or logs.

---

### Model Denial of Service
Attackers may overload the model with extremely complex or expensive prompts.

Can cause:
- service outages
- excessive API costs
- resource exhaustion

---

### Memory and Context Poisoning
Agent memory systems can be manipulated so that malicious information becomes persistent.

Examples:
- poisoned knowledge base
- malicious RAG documents
- tampered internal memory

---

### Agent Impersonation
Attackers impersonate agents or inject fake agent messages into systems.

Can lead to:
- false instructions
- unauthorized actions
- malicious code execution

---

### Autonomous Action Abuse
Agents capable of taking real-world actions introduce additional risk.

Examples:
- file deletion
- system command execution
- code commits
- network access

Security research shows prompt injection can cause coding agents to execute malicious commands.

---

### Credential Exposure
Agents interacting with external systems may accidentally leak credentials through:
- logs
- responses
- debug output

---

### Agent-to-Agent Trust Exploits
Multi-agent systems may assume other agents are trustworthy.

Attackers can exploit this trust by:
- sending malicious messages
- injecting false tasks
- spoofing agent identities

---

### Emerging Agent Threat Vectors
The OWASP Agentic AI Top 10 also identifies:
- human trust manipulation
- identity abuse
- unexpected autonomous behaviors

---

## Real-World Incident Examples

Security researchers have demonstrated prompt injection attacks capable of manipulating autonomous coding agents to run commands on user systems.
Source: https://www.lasso.security/blog/prompt-injection-examples

Prompt injection has been used to distribute malicious agent software through compromised development tools.
Source: https://www.theverge.com/ai-artificial-intelligence/881574/cline-openclaw-prompt-injection-hack

Indirect prompt injection attacks can trigger data exfiltration and malware execution if agents have broad permissions.
Source: https://www.techradar.com/pro/security/ibms-ai-bob-could-be-manipulated-to-download-and-execute-malware

---

## Where an Agent Should Look for Security Intelligence

Priority order:

1. OWASP GenAI Security Project — https://genai.owasp.org
2. OWASP LLM Top 10 — https://owasp.org/www-project-top-10-for-large-language-model-applications/
3. OWASP Agentic Top 10 — https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
4. MITRE ATLAS AI Threat Framework — https://atlas.mitre.org
5. AI Incident Database — https://incidentdatabase.ai
6. NIST AI Risk Management Framework — https://www.nist.gov/itl/ai-risk-management-framework

---

## Additional Security Research Sources

ArXiv AI Security Papers — https://arxiv.org/list/cs.CR/recent
Google Threat Intelligence — https://blog.google/threat-analysis-group/
Microsoft Security Research — https://www.microsoft.com/security/blog
Cisco AI Security Reports — https://blogs.cisco.com/ai
CrowdStrike AI Security Research — https://www.crowdstrike.com/blog

---

## Code Review Security Checklist for Agents

When performing secure code review, check for:

- [ ] Prompt injection exposure
- [ ] Unvalidated tool calls
- [ ] Excessive permissions
- [ ] Secret exposure
- [ ] Unsafe external requests
- [ ] Unsafe file system access
- [ ] Malicious dependency risk
- [ ] RAG document trust level
- [ ] Memory poisoning risk
- [ ] Agent-to-agent message validation
- [ ] Authentication and identity controls
- [ ] API rate limits and DoS protection

---

## Defensive Design Principles for Agent Systems

- Limit tool permissions
- Separate planning from execution
- Require confirmation for high-risk actions
- Never allow agents unrestricted system access
- Validate all external inputs
- Treat all external content as untrusted
- Log all autonomous actions
- Use human approval for critical operations

---

## Security Training Dataset Sources

- OWASP GenAI Top 10
- OWASP Agentic AI Top 10
- MITRE ATLAS threat taxonomy
- AI Incident Database
- ArXiv agent security research papers
- Security vendor threat intelligence reports
