import frappe
import subprocess
import os
import time
import errno
from frappe.model.document import Document
from frappe.utils.background_jobs import enqueue
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

    def validate(self):
        if self.delete_now and not self.mysql_root_password:
            frappe.msgprint("Warning: MySQL Root Password is empty. Deletion may fail if socket authentication is not enabled.")

    def on_update(self):
        frappe.log(f"on_update triggered for Site Deletion Request {self.name}")
        if self.delete_now and self.status == "Pending":
            frappe.log(f"Enqueuing deletion process for sites: {[site.site_name for site in self.sites_to_delete]}")
            self.status = "Processing"
            self.error_log = "Deletion process started in background. Check Error Log for updates.\n"
            self.save()
            frappe.db.commit()
            # Enqueue deletion as a background job
            enqueue(
                "site_cleaner.site_deletion_request.delete_sites",
                queue="long",
                timeout=1800,  # 30 minutes
                doc_name=self.name,
                sites=[site.site_name for site in self.sites_to_delete],
                mysql_root_password=self.mysql_root_password
            )

@frappe.whitelist()
def delete_sites(doc_name, sites, mysql_root_password):
    start_time = time.time()
    frappe.log(f"Starting background deletion for Site Deletion Request {doc_name}")
    doc = frappe.get_doc("Site Deletion Request", doc_name)
    doc.error_log = ""
    
    # Get bench path and sites path
    bench_path = frappe.utils.get_bench_path()
    sites_path = os.path.join(bench_path, "sites")
    sites_path = os.path.abspath(sites_path)
    frappe.log(f"Calculated sites_path: {sites_path}, bench_path: {bench_path}")

    if not os.path.exists(sites_path):
        frappe.log(f"Error: Sites directory does not exist at {sites_path}")
        doc.status = "Failed"
        doc.error_log = f"Error: Sites directory does not exist at {sites_path}\n"
        doc.save()
        frappe.db.commit()
        return

    deletion_attempted = False
    all_skipped = True

    for site_name in sites:
        site_name = site_name.strip()
        site_path = os.path.join(sites_path, site_name)
        site_start_time = time.time()
        
        frappe.log(f"Checking site {site_name} at path: {site_path}")
        
        # Check if site exists and diagnose issues
        if not os.path.exists(site_path):
            try:
                os.stat(site_path)
            except OSError as e:
                frappe.log(f"Site {site_name} does not exist. Error: {e}")
                doc.error_log += f"Skipped {site_name}: Site does not exist at {site_path}. Error: {e}\n"
            else:
                frappe.log(f"Site {site_name} does not exist (no specific error)")
                doc.error_log += f"Skipped {site_name}: Site does not exist at {site_path}\n"
            continue
        
        # Verify site_path is a directory
        if not os.path.isdir(site_path):
            frappe.log(f"Site {site_name} is not a directory")
            doc.error_log += f"Skipped {site_name}: Path {site_path} is not a directory\n"
            continue

        # Check permissions
        if not os.access(site_path, os.R_OK | os.X_OK):
            frappe.log(f"Site {site_name}: No permissions to read/execute {site_path}")
            doc.error_log += f"Skipped {site_name}: No read/execute permissions on {site_path}\n"
            continue

        deletion_attempted = True
        try:
            frappe.log(f"Attempting to delete site {site_name} with provided password")
            cmd = ["bench", "drop-site", site_name, "--force", "--root-password", mysql_root_password]
            result = subprocess.run(
                cmd,
                cwd=bench_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=300  # 5-minute timeout per site
            )
            frappe.log(f"Successfully deleted site {site_name} in {time.time() - site_start_time:.2f} seconds")
            doc.error_log += f"Successfully deleted {site_name}\n"
            all_skipped = False
        except subprocess.TimeoutExpired:
            frappe.log(f"Timeout deleting site {site_name}")
            doc.status = "Failed"
            doc.error_log += f"Failed to delete {site_name}: Operation timed out after 5 minutes\n"
            doc.save()
            frappe.db.commit()
            return
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.replace(mysql_root_password, "****") if mysql_root_password else e.stderr
            if "Access denied for user 'root'@'localhost'" in error_message:
                frappe.log(f"Password auth failed for {site_name}, attempting socket auth")
                try:
                    cmd = ["bench", "drop-site", site_name, "--force"]
                    result = subprocess.run(
                        cmd,
                        cwd=bench_path,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=300
                    )
                    frappe.log(f"Successfully deleted site {site_name} using socket auth in {time.time() - site_start_time:.2f} seconds")
                    doc.error_log += f"Successfully deleted {site_name} (socket auth)\n"
                    all_skipped = False
                except subprocess.TimeoutExpired:
                    frappe.log(f"Timeout deleting site {site_name} with socket auth")
                    doc.status = "Failed"
                    doc.error_log += f"Failed to delete {site_name}: Operation timed out after 5 minutes (socket auth)\n"
                    doc.save()
                    frappe.db.commit()
                    return
                except subprocess.CalledProcessError as e2:
                    error_message = e2.stderr
                    frappe.log(f"Socket auth failed for {site_name}: {error_message}")
                    doc.status = "Failed"
                    doc.error_log += f"Failed to delete {site_name}: {error_message}\n"
                    doc.save()
                    frappe.db.commit()
                    return
            else:
                frappe.log(f"Error deleting site {site_name}: {error_message}")
                doc.status = "Failed"
                doc.error_log += f"Failed to delete {site_name}: {error_message}\n"
                doc.save()
                frappe.db.commit()
                return

    # Determine final status
    if deletion_attempted and not all_skipped:
        doc.status = "Completed"
        doc.error_log += f"Deletion process completed successfully in {time.time() - start_time:.2f} seconds\n"
    elif all_skipped:
        doc.status = "Completed"
        doc.error_log += "No sites deleted: All selected sites do not exist or are inaccessible\n"
    else:
        doc.status = "Completed"
        doc.error_log += "No sites were selected for deletion\n"

    # Clear password for security
    doc.mysql_root_password = None
    doc.save()
    frappe.db.commit()
    frappe.log(f"Deletion process completed for Site Deletion Request {doc_name} in {time.time() - start_time:.2f} seconds")