(() => {
	const MENU_LABEL = __("Report Bug");
	const MENU_ATTR = "data-pulse-report-bug";

	function init() {
		$(document).on("app_ready", () => {
			attach_hooks();
			schedule_menu_injection();
		});

		if (window.frappe?.router) {
			attach_hooks();
			schedule_menu_injection();
		}
	}

	function attach_hooks() {
		if (window.__pulse_bug_menu_hooks_attached) return;
		window.__pulse_bug_menu_hooks_attached = true;

		frappe.router.on("change", () => {
			schedule_menu_injection();
		});

		$(document).on("render_complete", () => {
			schedule_menu_injection();
		});
	}

	function schedule_menu_injection() {
		[150, 500, 1000].forEach((delay) => {
			window.setTimeout(add_menu_item, delay);
		});
	}

	function add_menu_item() {
		if (frappe.session?.user === "Guest") return;

		const page = get_current_page();
		if (!page?.add_menu_item) return;

		const wrapper = page.menu?.parent?.() || page.wrapper;
		if (!wrapper) return;

		if ($(wrapper).find(`[${MENU_ATTR}="1"]`).length) return;

		const item = page.add_menu_item(MENU_LABEL, () => {
			show_report_bug_dialog();
		});

		if (item) {
			$(item).attr(MENU_ATTR, "1");
		}
	}

	function get_current_page() {
	return window.cur_frm?.page
		|| window.cur_list?.page
		|| frappe.container?.page
		|| null;
}

	function show_report_bug_dialog() {
		const context = get_bug_context();
		const dialog = new frappe.ui.Dialog({
			title: __("Report a Bug"),
			fields: [
				{
					fieldname: "title",
					fieldtype: "Data",
					label: __("Title"),
					reqd: 1,
				},
				{
					fieldname: "bug_type",
					fieldtype: "Select",
					label: __("Bug Type"),
					options: ["Bug", "Improvement", "Regression", "Support"].join("\n"),
					default: "Bug",
				},
				{
					fieldname: "priority",
					fieldtype: "Select",
					label: __("Priority"),
					options: ["Low", "Medium", "High", "Urgent"].join("\n"),
					default: "Medium",
				},
				{
					fieldname: "environment",
					fieldtype: "Select",
					label: __("Environment"),
					options: ["Production", "Staging"].join("\n"),
					default: infer_environment(),
				},
				{
					fieldname: "description",
					fieldtype: "Small Text",
					label: __("Description"),
					reqd: 1,
				},
				{
					fieldname: "steps_to_reproduce",
					fieldtype: "Small Text",
					label: __("Steps to Reproduce"),
				},
				{
					fieldname: "expected_result",
					fieldtype: "Small Text",
					label: __("Expected Result"),
				},
				{
					fieldname: "actual_result",
					fieldtype: "Small Text",
					label: __("Actual Result"),
				},
			],
			primary_action_label: __("Report Bug"),
			primary_action: async (values) => {
				const response = await frappe.call({
					method: "pulse.api.bugs.report_bug",
					args: {
						payload: values,
						context,
					},
					freeze: true,
					freeze_message: __("Creating bug report..."),
				});

				const bug = response.message || {};
				dialog.hide();
				if (bug.issue_key) {
					const link = bug.can_open
						? ` <a href="/pulse">${__("Open Pulse")}</a>`
						: "";
					frappe.show_alert(
						{
							message: __("Bug {0} reported.", [bug.issue_key]) + link,
							indicator: "green",
						},
						10
					);
				}
			},
		});

		dialog.show();
	}

	function get_bug_context() {
		const route = frappe.get_route() || [];
		const route_str = frappe.get_route_str();
		const list_view = frappe.container?.page?.list_view;
		const query_report = frappe.query_report;
		const context = {
			page_route: route_str,
			reference_doctype: null,
			reference_name: null,
			module_name: null,
			report_name: null,
		};

		if (window.cur_frm?.doctype && window.cur_frm?.docname) {
			context.reference_doctype = window.cur_frm.doctype;
			context.reference_name = window.cur_frm.docname;
			context.module_name = window.cur_frm.meta?.module || null;
			return context;
		}

		if (list_view?.doctype) {
			context.reference_doctype = list_view.doctype;
			context.module_name = list_view.meta?.module || null;
			return context;
		}

		if (query_report?.report_name) {
			context.report_name = query_report.report_name;
		}

		if (route[0] === "query-report" && route[1]) {
			context.report_name = route[1];
		}

		if (route[0] === "List" && route[1]) {
			context.reference_doctype = route[1];
		}

		if (route[0] === "Form" && route[1]) {
			context.reference_doctype = route[1];
			context.reference_name = route[2] || null;
		}

		return context;
	}

	function infer_environment() {
		const env = (frappe.boot?.environment || "").toLowerCase();
		return env === "production" ? "Production" : "Staging";
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
