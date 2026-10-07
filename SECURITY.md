# Security reporting

Do not post credentials, customer data, exploit details or raw cloud responses in
public issues. If the repository enables GitHub private vulnerability reporting,
use its **Security → Report a vulnerability** form. If it is unavailable, request
a private contact channel from the maintainer without disclosing vulnerability
details publicly. No dedicated security email or response SLA is established.

Include affected source/version, a synthetic reproduction, impact and relevant
denial/scope boundaries. Operators retain responsibility for their own AWS account,
identity provider, hosting, telemetry, data classification, costs and incident response.

The project is locally tested and has not completed live production qualification.
Before production use, complete [customer acceptance](docs/PRODUCTION_CHECKLIST.md)
and rehearse [security operations](docs/SECURITY_OPERATIONS.md).
