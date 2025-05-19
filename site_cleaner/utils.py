import os
import frappe

def get_bench_sites():
    """
    Fetch all site directories in the Frappe bench's sites directory.
    Returns a list of site names.
    """
    try:
        # Calculate sites path relative to the bench directory
        sites_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sites"))
        frappe.log(f"Calculated sites path: {sites_path}")
        
        # Verify the directory exists
        if not os.path.exists(sites_path):
            frappe.log(f"Sites directory does not exist: {sites_path}")
            return []
        
        # Get all directories in sites_path
        sites = [d for d in os.listdir(sites_path) if os.path.isdir(os.path.join(sites_path, d))]
        frappe.log(f"Found sites: {sites}")
        return sites
    except Exception as e:
        frappe.log(f"Error fetching sites: {str(e)}")
        return []