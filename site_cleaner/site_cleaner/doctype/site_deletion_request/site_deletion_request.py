import frappe
import subprocess
import os
from frappe.model.document import Document
from site_cleaner.utils import get_bench_sites

class SiteDeletionRequest(Document):
    def before_save(self):
        if not self.sites_to_delete:
            frappe.log(f"Populating sites_to_delete for Site Deletion Request {self.name}")
            sites = get_bench_sites()
            if not sites:
                frappe.log("No sites found to populate")
                self.error_log = "No sites found in the bench directory\n"
            for site in sites:
                self.append("sites_to_delete", {"site_name": site})
            frappe.log(f"Populated sites_to_delete with: {sites}")

    def on_update(self):
        frappe.log(f"on_update triggered for Site Deletion Request {self.name}")
        if self.delete_now and self.status == "Pending":
            frappe.log(f"Starting deletion process for sites: {[site.site_name for site in self.sites_to_delete]}")
            self.status = "Processing"
            self.error_log = ""  # Initialize error_log
            self.save()
            frappe.db.commit()
            
            # Compute bench path dynamically
            sites_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "sites"))
            bench_path = os.path.dirname(sites_path)
            frappe.log(f"Bench path: {bench_path}")
            
            # Fetch MySQL root password from common_site_config.json
            mysql_root_password = frappe.get_conf().get("db_root_password", "system")
            
            deletion_attempted = False  # Track if any deletion was attempted
            all_skipped = True  # Track if all sites were skipped
            
            for site in self.sites_to_delete:
                site_name = site.site_name
                site_path = os.path.join(sites_path, site_name)
                
                # Check if site exists
                if not os.path.exists(site_path):
                    frappe.log(f"Skipping site {site_name}: Site does not exist")
                    self.error_log += f"Skipped {site_name}: Site does not exist\n"
                    continue
                
                # Site exists, attempt deletion
                deletion_attempted = True
                try:
                    frappe.log(f"Attempting to delete site {site_name}")
                    # Run bench drop-site command
                    result = subprocess.run(
                        ["bench", "drop-site", site_name, "--force", "--root-password", mysql_root_password],
                        cwd=bench_path,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    frappe.log(f"Successfully deleted site {site_name}: {result.stdout}")
                    self.error_log += f"Successfully deleted {site_name}\n"
                    all_skipped = False
                except subprocess.CalledProcessError as e:
                    frappe.log(f"Error deleting site {site_name}: {e.stderr}")
                    self.status = "Failed"
                    self.error_log += f"Failed to delete {site_name}: {e.stderr}\n"
                    self.save()
                    frappe.db.commit()
                    return
            
            # Determine final status
            if deletion_attempted and not all_skipped:
                self.status = "Completed"
                self.error_log += "Deletion process completed successfully\n"
            elif all_skipped:
                self.status = "Completed"
                self.error_log += "No sites deleted: All selected sites do not exist\n"
            else:
                self.status = "Completed"
                self.error_log += "No sites were selected for deletion\n"
            
            self.save()
            frappe.db.commit()
            frappe.log(f"Deletion process completed for Site Deletion Request {self.name}")