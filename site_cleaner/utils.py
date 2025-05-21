import os
import frappe
@frappe.whitelist(allow_guest=True)
def get_bench_sites():
    """
    Fetch all site directories in the Frappe bench's sites directory.
    Returns a list of site names.
    """
    try:
        # Get bench path and sites path
        bench_path = frappe.utils.get_bench_path()  # e.g., /home/ubuntu/frappe-bench
        sites_path = os.path.join(bench_path, "sites")  # e.g., /home/ubuntu/frappe-bench/sites
        sites_path = os.path.abspath(sites_path)
        frappe.log(f"Calculated sites path: {sites_path}")

        if not os.path.exists(sites_path):
            frappe.log(f"Sites directory does not exist: {sites_path}")
            return []

        sites = [d for d in os.listdir(sites_path) if os.path.isdir(os.path.join(sites_path, d))]
        frappe.log(f"Found sites: {sites}")
        return sites
    except Exception as e:
        frappe.log(f"Error fetching sites: {str(e)}")
        return []