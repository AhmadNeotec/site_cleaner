import os
import frappe
@frappe.whitelist(allow_guest=True)
def get_bench_sites():
    bench_path = frappe.utils.get_bench_path()
    sites_path = os.path.join(bench_path, "sites")
    if not os.path.exists(sites_path):
        return []
    sites = []
    for site in os.listdir(sites_path):
        site_path = os.path.join(sites_path, site)
        if os.path.isdir(site_path) and os.path.exists(os.path.join(site_path, "site_config.json")):
            sites.append(site)
    return sites