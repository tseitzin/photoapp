import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConfirmDialog from '../ConfirmDialog.vue'

describe('ConfirmDialog', () => {
  it('emits confirm when the confirm button is clicked', async () => {
    const wrapper = mount(ConfirmDialog, { props: { title: 'Sure?' } })

    await wrapper.get('.btn--primary').trigger('click')

    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('emits cancel from the cancel button and the backdrop', async () => {
    const wrapper = mount(ConfirmDialog, { props: { title: 'Sure?' } })

    await wrapper.get('.btn:not(.btn--primary)').trigger('click')
    await wrapper.get('.backdrop').trigger('click')

    expect(wrapper.emitted('cancel')).toHaveLength(2)
  })

  it('keeps confirm disabled until the exact phrase is typed', async () => {
    const wrapper = mount(ConfirmDialog, {
      props: { title: 'Delete?', danger: true, typeToConfirm: 'DELETE' },
    })
    const confirm = wrapper.get('.btn--danger')

    expect(confirm.attributes('disabled')).toBeDefined()

    await wrapper.get('.type-input').setValue('delete')
    expect(confirm.attributes('disabled')).toBeDefined()

    await wrapper.get('.type-input').setValue('DELETE')
    expect(confirm.attributes('disabled')).toBeUndefined()

    await confirm.trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })
})
