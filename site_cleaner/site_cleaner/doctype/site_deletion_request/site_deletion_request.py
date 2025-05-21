import frappe
import subprocess
import os
import sys
from frappe.model.document import Document
from site_cleaner.utils import get_bench_sites

def test_mysql_connection(mysql_root_password):
    """Test MySQL connection with provided password."""
    try:
        cmd = ["mysql", "-u", "root", "-e", "SELECT 1"]
        if mysql_root_password:
            cmd.insert(3, f"-p{mysql_root_password}")
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10
        )
        frappe.log("MySQL connection test successful")
        return True
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.replace(mysql_root_password, "****") if mysql_root_password else e.stderr
        frappe.log(f"MySQL connection test failed: {error_message}")
        return False
    except subprocess.TimeoutExpired:
        frappe.log("MySQL connection test timed out")
        return False

@frappe.whitelist()
def populate_sites(doc_name):
    """Populate sites_to_delete with all available sites."""
    doc = frappe.get_doc("Site Deletion Request", doc_name)
    doc.sites_to_delete = []
    sites = get_bench_sites()
    if not sites:
        doc.error_log = "No sites found in the bench directory\n"
        doc.save()
        frappe.db.commit()
        return
    for site in sites:
        doc.append("sites_to_delete", {
            "site_name": site,
            "delete": 0
        })
    doc.save()
    frappe.db.commit()
    frappe.log(f"Populated sites_to_delete with: {sites}")

class SiteDeletionRequest(Document):
    def validate(self):
        mysql_root_password = getattr(self, 'mysql_root_password', '')
        if self.delete_now and not mysql_root_password:
            frappe.msgprint("Warning: MySQL Root Password is empty. Will attempt socket authentication.")
        if self.delete_now and not any(site.delete for site in self.sites_to_delete):
            frappe.msgprint("No sites selected for deletion. Please check the 'Delete' box for sites to delete.")

    def on_update(self):
        frappe.log(f"on_update triggered for Site Deletion Request {self.name}")
        if self.delete_now and self.status == "Pending":
            selected_sites = [site.site_name for site in self.sites_to_delete if site.delete]
            if not selected_sites:
                frappe.log("No sites selected for deletion")
                self.status = "Failed"
                self.error_log = "No sites selected for deletion\n"
                self.save()
                frappe.db.commit()
                raise frappe.ValidationError("No sites selected for deletion")
            frappe.log(f"Starting synchronous deletion for sites: {selected_sites}")
            self.status = "Processing"
            self.error_log = "Deletion process started...\n"
            self.save()
            frappe.db.commit()
            try:
                self.delete_sites_synchronously()
                self.status = "Completed"
                self.error_log += "Deletion process completed successfully\n"
            except Exception as e:
                frappe.log(f"Deletion failed: {str(e)}")
                self.status = "Failed"
                self.error_log += f"Deletion failed: {str(e)}\n"
                self.save()
                frappe.db.commit()
                raise frappe.ValidationError(f"Deletion failed: {str(e)}")
            self.save()
            frappe.db.commit()

    def delete_sites_synchronously(self):
        bench_path = frappe.utils.get_bench_path()
        sites_path = os.path.join(bench_path, "sites")
        sites_path = os.path.abspath(sites_path)
        frappe.log(f"Calculated sites_path: {sites_path}, bench_path: {bench_path}")

        mysql_root_password = getattr(self, 'mysql_root_password', '').strip()
        deletion_attempted = False
        all_skipped = True

        # Test MySQL connection if password is provided
        if mysql_root_password and not test_mysql_connection(mysql_root_password):
            error_msg = "Invalid MySQL root password"
            self.error_log += f"Failed: {error_msg}\n"
            raise frappe.ValidationError(error_msg)

        for site in self.sites_to_delete:
            if not site.delete:
                frappe.log(f"Skipping site {site.site_name}: Not selected for deletion")
                continue
            site_name = site.site_name.strip()
            site_path = os.path.join(sites_path, site_name)
            frappe.log(f"Checking site {site_name} at path: {site_path}")

            if not os.path.exists(site_path):
                frappe.log(f"Site {site_name} does not exist")
                self.error_log += f"Skipped {site_name}: Site does not exist at {site_path}\n"
                continue

            if not os.path.isdir(site_path):
                frappe.log(f"Site {site_name} is not a directory")
                self.error_log += f"Skipped {site_name}: Path {site_path} is not a directory\n"
                continue

            if not os.access(site_path, os.R_OK | os.X_OK):
                frappe.log(f"Site {site_name}: No permissions to read/execute {site_path}")
                self.error_log += f"Skipped {site_name}: No read/execute permissions on {site_path}\n"
                continue

            if not os.path.exists(os.path.join(site_path, "site_config.json")):
                frappe.log(f"Site {site_name}: Not a valid Frappe site (missing site_config.json)")
                self.error_log += f"Skipped {site_name}: Not a valid Frappe site (missing site_config.json)\n"
                continue

            deletion_attempted = True
            try:
                frappe.log(f"Attempting to delete site {site_name}")
                print(f"*** ATTEMPTING TO DELETE SITE: {site_name} ***", file=sys.stderr)
                cmd = ["bench", "drop-site", site_name, "--force", "--no-backup"]
                if mysql_root_password:
                    cmd.extend(["--db-root-password", mysql_root_password])
                frappe.log(f"Executing command: {' '.join(cmd[:-2] if mysql_root_password else cmd)} [HIDDEN]")
                process = subprocess.run(
                    cmd,
                    cwd=bench_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                    timeout=15
                )
                frappe.log(f"Successfully deleted site {site_name}")
                self.error_log += f"Successfully deleted {site_name}\n"
                all_skipped = False
            except subprocess.TimeoutExpired:
                frappe.log(f"Timeout deleting site {site_name}")
                self.error_log += f"Failed to delete {site_name}: Operation timed out after 15 seconds\n"
                raise
            except subprocess.CalledProcessError as e:
                error_message = e.stderr.replace(mysql_root_password, "****") if mysql_root_password else e.stderr
                frappe.log(f"Error deleting site {site_name}: {error_message}")
                self.error_log += f"Failed to delete {site_name}: {error_message}\n"
                if "Access denied for user 'root'@'localhost'" in error_message and mysql_root_password:
                    frappe.log(f"Attempting socket auth for {site_name}")
                    try:
                        cmd = ["bench", "drop-site", site_name, "--force", "--no-backup"]
                        process = subprocess.run(
                            cmd,
                            cwd=bench_path,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            check=True,
                            timeout=15
                        )
                        frappe.log(f"Successfully deleted site {site_name} using socket auth")
                        self.error_log += f"Successfully deleted {site_name} (socket auth)\n"
                        all_skipped = False
                    except subprocess.TimeoutExpired:
                        frappe.log(f"Timeout deleting site {site_name} with socket auth")
                        self.error_log += f"Failed to delete {site_name}: Operation timed out after 15 seconds (socket auth)\n"
                        raise
                    except subprocess.CalledProcessError as e2:
                        error_message = e2.stderr
                        frappe.log(f"Socket auth failed for {site_name}: {error_message}")
                        self.error_log += f"Failed to delete {site_name}: {error_message}\n"
                        raise

        if not deletion_attempted:
            self.error_log += "No sites were selected for deletion\n"
        elif all_skipped:
            self.error_log += "No sites deleted: All selected sites do not exist or are inaccessible\n"