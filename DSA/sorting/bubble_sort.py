def bubble_sort(nums):
    for i in range(len(nums) - 1):
        for j in range(len(nums) - 1 - i):
            if nums[j] > nums[j + 1]:
                nums[j], nums[j + 1] = nums[j + 1], nums[j]
    return nums



def bubble_sort_desc(nums):
    for i in range(len(nums)-1, 0, -1):
        for j in range(i):
            if nums[j] < nums[j+1]:
                nums[j], nums[j+1] = nums[j+1], nums[j]
    return nums


"""
Optimized code using Is_swap
TC -O(N)
SC - O(1)
"""

def bubble_sort_swap(nums):
    for i in range(len(nums) - 1):
        is_swap = False
        for j in range(len(nums) - 1 - i):
            if nums[j] > nums[j + 1]:
                nums[j], nums[j + 1] = nums[j + 1], nums[j]
                is_swap = True
        if not is_swap:
            break
    return nums