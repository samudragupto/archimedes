"""Service layer: Nebius Token Factory client, Tavily research, document parsing,
Supabase storage, job launching and export. All stateless except for injected
HTTP clients, so both the API and the worker can use them interchangeably."""
