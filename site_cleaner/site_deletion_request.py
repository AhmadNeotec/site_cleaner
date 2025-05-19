import frappe
import os
from frappe.model.document import Document

class SiteDeletionRequest(Document):
    def before_save(self):
        if not self.sites_to_delete:
            # Fetch all sites from the sites directory
            bench_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "sites"))
            sites = [d for d in os.listdir(bench_path) if os.path.isdir(os.path.join(bench_path, d))]
            for site in sites:
                self.append("sites_to_delete", {"site_name": site})