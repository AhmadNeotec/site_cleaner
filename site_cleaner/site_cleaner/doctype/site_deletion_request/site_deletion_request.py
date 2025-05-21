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
            self.error_log = ""
            self.save()
            frappe.db.commit()

            # Get bench path and sites path
            bench_path = frappe.utils.get_bench_path()  # e.g., /home/ubuntu/frappe-bench
            sites_path = os.path.join(bench_path, "sites")  # e.g., /home/ubuntu/frappe-bench/sites
            sites_path = os.path.abspath(sites_path)
            frappe.log(f"Calculated sites_path: {sites_path}, bench_path: {bench_path}")

            # Verify sites_path exists
            if not os.path.exists(sites_path):
                frappe.log(f"Error: Sites directory does not exist at {sites_path}")
                self.status = "Failed"
                self.error_log = f"Error: Sites directory does not exist at {sites_path}\n"
                self.save()
                frappe.db.commit()
                return
            
            # Get MySQL root password - IMPROVED PASSWORD HANDLING
            mysql_root_password = self.mysql_root_password
            if not mysql_root_password:
                mysql_root_password = frappe.get_conf().get("db_root_password", "")
                
            # Validate we have a password
            if not mysql_root_password:
                self.status = "Failed"
                self.error_log = "MySQL root password is required but not provided\n"
                self.save()
                frappe.db.commit()
                return

            # Log password length for debugging
            frappe.log(f"MySQL password length: {len(mysql_root_password) if mysql_root_password else 0}")

            deletion_attempted = False
            all_skipped = True

            for site in self.sites_to_delete:
                site_name = site.site_name.strip()
                site_path = os.path.join(sites_path, site_name)
                
                frappe.log(f"Checking site {site_name} at path: {site_path}")
                
                # Check if site exists
                if not os.path.exists(site_path):
                    frappe.log(f"Skipping site {site_name}: Site does not exist at {site_path}")
                    self.error_log += f"Skipped {site_name}: Site does not exist at {site_path}\n"
                    continue
                
                # Verify site_path is a directory
                if not os.path.isdir(site_path):
                    frappe.log(f"Skipping site {site_name}: Path {site_path} is not a directory")
                    self.error_log += f"Skipped {site_name}: Path {site_path} is not a directory\n"
                    continue

                deletion_attempted = True
                try:
                    frappe.log(f"Attempting to delete site {site_name}")
                    
                    # Set environment with the password - IMPROVED METHOD
                    env = os.environ.copy()
                    env["MYSQL_PWD"] = mysql_root_password
                    
                    # Run the command without exposing password on command line
                    result = subprocess.run(
                        ["bench", "drop-site", site_name, "--force"],
                        cwd=bench_path,
                        env=env,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    
                    frappe.log(f"Successfully deleted site {site_name}")
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
