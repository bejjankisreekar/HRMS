"""Marketing copy and structure for the Features page."""

from __future__ import annotations

FEATURE_CATEGORIES = [
    {
        "id": "core-hr",
        "title": "Core HR",
        "subtitle": "Centralize people data, org structure, and documents in one secure hub.",
        "icon": "users",
        "accent": "violet",
        "items": [
            {
                "title": "Employee Management",
                "description": "Complete profiles, job history, reporting lines, and lifecycle tracking from hire to exit.",
                "icon": "user-cog",
            },
            {
                "title": "Department Management",
                "description": "Organize teams, cost centers, and hierarchies with drag-friendly department trees.",
                "icon": "layers",
            },
            {
                "title": "Document Management",
                "description": "Store contracts, IDs, and policy acknowledgements with version control and access rules.",
                "icon": "folder-lock",
            },
            {
                "title": "Organization Structure",
                "description": "Interactive org charts, team views, and reporting relationships at a glance.",
                "icon": "git-branch",
            },
        ],
    },
    {
        "id": "attendance",
        "title": "Attendance & Time Tracking",
        "subtitle": "Capture time accurately with shifts, geo rules, and real-time visibility.",
        "icon": "calendar-check",
        "accent": "cyan",
        "items": [
            {
                "title": "Biometric Integration",
                "description": "Connect fingerprint and face devices for automated, tamper-proof check-ins.",
                "icon": "fingerprint",
            },
            {
                "title": "Shift Scheduling",
                "description": "Build rotations, assign shifts, and manage swap requests without spreadsheets.",
                "icon": "calendar-clock",
            },
            {
                "title": "Geo Attendance",
                "description": "Validate presence with geofenced locations and mobile check-in for field teams.",
                "icon": "map-pin",
            },
            {
                "title": "Overtime Tracking",
                "description": "Auto-calculate OT hours against policies and route for manager approval.",
                "icon": "timer",
            },
            {
                "title": "Late / Early Reports",
                "description": "Instant punctuality dashboards with trend alerts for HR and team leads.",
                "icon": "alarm-clock",
            },
        ],
    },
    {
        "id": "payroll",
        "title": "Payroll",
        "subtitle": "Run compliant payroll cycles with confidence and full audit trails.",
        "icon": "wallet",
        "accent": "indigo",
        "items": [
            {
                "title": "Automated Salary Processing",
                "description": "One-click payroll runs with attendance and leave data synced automatically.",
                "icon": "calculator",
            },
            {
                "title": "Tax Calculations",
                "description": "Configurable tax slabs, deductions, and statutory components built in.",
                "icon": "receipt",
            },
            {
                "title": "Payslip Generation",
                "description": "Branded digital payslips delivered to employee portals and email.",
                "icon": "file-text",
            },
            {
                "title": "Bonus & Incentives",
                "description": "Variable pay, commissions, and one-time bonuses tied to performance rules.",
                "icon": "gift",
            },
            {
                "title": "Compliance Management",
                "description": "PF, ESI, and regional compliance reports ready for filing.",
                "icon": "shield-check",
            },
        ],
    },
    {
        "id": "leave",
        "title": "Leave Management",
        "subtitle": "Flexible policies, smooth approvals, and always-accurate balances.",
        "icon": "palmtree",
        "accent": "emerald",
        "items": [
            {
                "title": "Leave Requests",
                "description": "Self-service applications with attachments and half-day options.",
                "icon": "send",
            },
            {
                "title": "Approval Workflow",
                "description": "Multi-level approvers, delegations, and SLA reminders.",
                "icon": "git-merge",
            },
            {
                "title": "Holiday Calendar",
                "description": "Org-wide and location-specific holiday calendars synced to attendance.",
                "icon": "calendar-days",
            },
            {
                "title": "Leave Balances",
                "description": "Real-time accruals, carry-forward rules, and encashment tracking.",
                "icon": "scale",
            },
        ],
    },
    {
        "id": "ess",
        "title": "Employee Self Service",
        "subtitle": "Empower employees to manage their work life without HR bottlenecks.",
        "icon": "smartphone",
        "accent": "amber",
        "items": [
            {
                "title": "Apply Leave",
                "description": "Submit and track leave from web or mobile in seconds.",
                "icon": "calendar-plus",
            },
            {
                "title": "Download Payslips",
                "description": "Secure access to current and historical payslips anytime.",
                "icon": "download",
            },
            {
                "title": "Update Profile",
                "description": "Edit contact info, emergency contacts, and upload documents.",
                "icon": "user-pen",
            },
            {
                "title": "Expense Claims",
                "description": "Submit reimbursements with receipts and approval routing.",
                "icon": "credit-card",
            },
        ],
    },
    {
        "id": "performance",
        "title": "Performance Management",
        "subtitle": "Align goals, measure progress, and grow your people systematically.",
        "icon": "target",
        "accent": "purple",
        "items": [
            {
                "title": "Goals",
                "description": "OKRs and KPIs cascaded from company to individual contributors.",
                "icon": "flag",
            },
            {
                "title": "Appraisals",
                "description": "Structured review cycles with self, peer, and manager assessments.",
                "icon": "star",
            },
            {
                "title": "KPI Tracking",
                "description": "Live scorecards with thresholds and progress visualizations.",
                "icon": "gauge",
            },
            {
                "title": "Feedback System",
                "description": "Continuous feedback, 360 reviews, and recognition moments.",
                "icon": "message-circle",
            },
        ],
    },
    {
        "id": "analytics",
        "title": "Reports & Analytics",
        "subtitle": "Turn HR data into decisions with export-ready insights.",
        "icon": "bar-chart-3",
        "accent": "blue",
        "items": [
            {
                "title": "HR Reports",
                "description": "Headcount, turnover, and diversity metrics in one click.",
                "icon": "file-bar-chart",
            },
            {
                "title": "Attendance Reports",
                "description": "Daily, weekly, and monthly attendance with drill-down filters.",
                "icon": "clipboard-list",
            },
            {
                "title": "Payroll Reports",
                "description": "Cost center summaries, variance analysis, and statutory exports.",
                "icon": "pie-chart",
            },
            {
                "title": "Employee Analytics",
                "description": "Trend dashboards for engagement, tenure, and productivity signals.",
                "icon": "trending-up",
            },
        ],
    },
]

COMPARISON_ROWS = [
    ("Setup time", "Weeks of custom dev", "Live in days"),
    ("Multi-tenant SaaS", "Single instance", "Built-in org isolation"),
    ("Role-based access", "Manual permissions", "Super Admin → Employee roles"),
    ("Mobile experience", "Desktop-only legacy", "Responsive + mobile-first"),
    ("API & integrations", "Closed system", "REST API + JWT ready"),
    ("Updates & security", "Manual patches", "Cloud updates + audit logs"),
]

ENTERPRISE_FEATURES = [
    ("Multi-tenant architecture", "Isolated workspaces per organization with secure data boundaries.", "building-2"),
    ("Role-based permissions", "Granular access for admins, HR, managers, and employees.", "key-round"),
    ("Audit logs", "Track who changed what, when — compliance ready.", "scroll-text"),
    ("API ready", "DRF + JWT endpoints for custom apps and integrations.", "code-2"),
    ("Cloud deployment", "Scalable infrastructure with 99.9% uptime target.", "cloud"),
    ("Security compliance", "Encryption, session security, and tenant isolation by design.", "lock"),
]

INTEGRATIONS = [
    ("Biometric devices", "fingerprint"),
    ("Email", "mail"),
    ("Slack", "slack"),
    ("WhatsApp", "message-circle"),
    ("Payroll APIs", "landmark"),
    ("Google Workspace", "chrome"),
]

def get_features_page_context() -> dict:
    return {
        "feature_categories": FEATURE_CATEGORIES,
        "comparison_rows": COMPARISON_ROWS,
        "enterprise_features": ENTERPRISE_FEATURES,
        "integrations": INTEGRATIONS,
    }
