output "backend_url" {
  value = module.backend.endpoint
}
output "frontend_url" {
  value = module.frontend.endpoint
}
output "registry_endpoint" {
  value = module.registry.endpoint
}
output "arena_job_id" {
  value = scaleway_job_definition.arena.id
}

output "site_url" {
  value = local.public_url != "" ? local.public_url : module.frontend.endpoint
}

# Enregistrements DNS à poser chez Cloudflare (tous en « DNS only »). `name` est le nom
# relatif, à taper tel quel dans le champ « Name » de Cloudflare (qui ajoute lui-même le
# domaine) ; « @ » = le domaine lui-même. Scaleway donne certains noms complets, avec ou
# sans le domaine et un point final : on les ramène tous à la forme relative.
locals {
  dns_name = { for k, n in {
    dkim  = try(scaleway_tem_domain.mail[0].dkim_name, "")
    dmarc = try(scaleway_tem_domain.mail[0].dmarc_name, "")
  } : k => trimsuffix(trimsuffix(trimsuffix(n, "."), var.domain), ".") }
}

output "dns_records" {
  value = local.has_domain ? [
    { type = "CNAME", name = "@", value = trimprefix(module.frontend.endpoint, "https://"), note = "site (avant le premier apply)" },
    # Scaleway ne donne que le fragment « include:… » : l'enregistrement SPF complet l'entoure.
    { type = "TXT", name = "@", value = "v=spf1 ${scaleway_tem_domain.mail[0].spf_config} -all", note = "emails : SPF" },
    { type = "TXT", name = local.dns_name.dkim, value = scaleway_tem_domain.mail[0].dkim_config, note = "emails : DKIM" },
    { type = "TXT", name = local.dns_name.dmarc, value = scaleway_tem_domain.mail[0].dmarc_config, note = "emails : DMARC" },
  ] : []
}
