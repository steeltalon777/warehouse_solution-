# Role Matrix

## Roles
- root
- chief_storekeeper
- storekeeper
- observer

## Permissions

| Action                 | root | chief_storekeeper | storekeeper | observer |
|------------------------|------|-------------------|-------------|----------|
| View data              | YES  | YES               | YES         | YES      |
| Create draft operation | YES  | YES               | YES (allowed scope only) | YES (if UI allows draft creation) |
| Submit operation       | YES  | YES               | YES (allowed scope only) | NO       |
| Cancel operation       | YES  | YES               | Own drafts only | NO       |
| Accept incoming goods  | YES  | YES               | YES (destination site only) | NO       |
| Manage catalog         | YES  | YES               | NO          | NO       |
| Manage users           | YES  | NO                | NO          | NO       |
