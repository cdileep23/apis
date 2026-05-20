def insertion_sort(nums):
    for i in range(1, len(nums)):
        key = nums[i]
        j = i - 1

        while j >= 0 and nums[j] > key:
            nums[j + 1] = nums[j]
            j -= 1

        nums[j + 1] = key
    return nums


"""
Descending order using insertion sort
"""

def insertion_sort_desc(nums):
    for i in range(1, len(nums)):
        key = nums[i]
        j = i - 1

        while j >= 0 and nums[j] < key:
            nums[j + 1] = nums[j]
            j -= 1

        nums[j + 1] = key
    return nums
