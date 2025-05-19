frappe.ui.form.on('Site Deletion Request', {
    refresh: function(frm) {
        frm.add_custom_button(__('Refresh Sites'), function() {
            frappe.call({
                method: "site_cleaner.utils.get_bench_sites",
                callback: function(r) {
                    frm.clear_table('sites_to_delete');
                    r.message.forEach(function(site) {
                        frm.add_child('sites_to_delete', {site_name: site});
                    });
                    frm.refresh_field('sites_to_delete');
                }
            });
        });
    }
});