// Copyright (c) 2016, Frappe and contributors
// Edtools override: fix course filter - use server get_program_courses, avoid frm.program_courses.map when undefined

frappe.ui.form.on('Program Enrollment', {
  onload: function (frm) {
    frm.set_query('academic_term', function () {
      return {
        filters: {
          academic_year: frm.doc.academic_year,
        },
      }
    })

    frm.set_query('academic_term', 'fees', function () {
      return {
        filters: {
          academic_year: frm.doc.academic_year,
        },
      }
    })

    frm.fields_dict['fees'].grid.get_field('fee_schedule').get_query =
      function (doc, cdt, cdn) {
        var d = locals[cdt][cdn]
        return {
          filters: { academic_term: d.academic_term },
        }
      }

    if (frm.doc.program) {
      _set_course_query(frm)
    }

    // Remove automatic academic_year filter - show all enabled students
    frm.set_query('student', function() {
      return {
        filters: {
          'enabled': 1
        }
      }
    });
  },

  program: function (frm) {
    frm.events.get_courses(frm)
    if (frm.doc.program) {
      _set_course_query(frm)
      frappe.call({
        method: 'education.education.api.get_fee_schedule',
        args: {
          program: frm.doc.program,
          student_category: frm.doc.student_category,
        },
        callback: function (r) {
          if (r.message) {
            frm.set_value('fees', r.message)
            frm.events.get_courses(frm)
          }
        },
      })
    }
  },

  student_category: function () {
    frappe.ui.form.trigger('Program Enrollment', 'program')
  },

  get_courses: function (frm) {
    frm.program_courses = []
    frm.set_value('courses', [])
    frappe.call({
      method: 'get_courses',
      doc: frm.doc,
      callback: function (r) {
        if (r.message) {
          frm.program_courses = r.message
          frm.set_value('courses', r.message)
        }
      },
    })
  },
})

function _set_course_query(frm) {
  if (!frm.doc.program) return
  frm.set_query('course', 'courses', function () {
    return {
      query: 'education.education.doctype.program_enrollment.program_enrollment.get_program_courses',
      filters: { program: frm.doc.program },
    }
  })
}

frappe.ui.form.on('Program Enrollment Course', {
  courses_add: function (frm) {
    // Do NOT override get_query with frm.program_courses.map - it is undefined when
    // opening existing/submitted docs. Use server get_program_courses (set in onload/program).
  },
})
