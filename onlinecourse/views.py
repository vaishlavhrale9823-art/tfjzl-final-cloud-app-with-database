
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
import logging

from .models import Course, Enrollment, Question, Choice, Submission

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}

    if request.method == 'GET':
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context
        )

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']

        if User.objects.filter(username=username).exists():
            context['message'] = "User already exists."
            return render(
                request,
                'onlinecourse/user_registration_bootstrap.html',
                context
            )

        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=password
        )
        login(request, user)
        return redirect("onlinecourse:index")


def login_request(request):
    context = {}

    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']
        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = "Invalid username or password."
        return render(
            request,
            'onlinecourse/user_login_bootstrap.html',
            context
        )

    return render(
        request,
        'onlinecourse/user_login_bootstrap.html',
        context
    )


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    if user.is_authenticated:
        return Enrollment.objects.filter(
            user=user,
            course=course
        ).exists()

    return False


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]

        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_details_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    if user.is_authenticated and not check_if_enrolled(user, course):
        Enrollment.objects.create(
            user=user,
            course=course,
            mode='honor'
        )
        course.total_enrollment += 1
        course.save(update_fields=['total_enrollment'])

    return HttpResponseRedirect(
        reverse('onlinecourse:course_details', args=(course.id,))
    )


def submit(request, course_id):
    if request.method != 'POST':
        return redirect(
            'onlinecourse:course_details',
            pk=course_id
        )

    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(Course, pk=course_id)

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    selected_choice_ids = extract_answers(request)

    # Validate submitted choice IDs before creating the submission.
    choices = []
    for choice_id in selected_choice_ids:
        choice = get_object_or_404(
            Choice,
            pk=choice_id,
            question__course=course
        )
        choices.append(choice)

    submission = Submission.objects.create(enrollment=enrollment)
    submission.choices.set(choices)

    return redirect(
        'onlinecourse:show_exam_result',
        course_id=course.id,
        submission_id=submission.id
    )


def extract_answers(request):
    submitted_answers = []

    for key in request.POST:
        if key.startswith('choice_'):
            for value in request.POST.getlist(key):
                try:
                    submitted_answers.append(int(value))
                except (TypeError, ValueError):
                    continue

    # Remove duplicate IDs while preserving order.
    return list(dict.fromkeys(submitted_answers))


def show_exam_result(request, course_id, submission_id):
    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__course=course,
        enrollment__user=request.user
    )

    questions = Question.objects.filter(
        course=course
    ).prefetch_related('choice_set')

    selected_ids = list(
        submission.choices.values_list('id', flat=True)
    )

    possible = sum(question.grade for question in questions)
    total_score = sum(
        question.is_get_score(selected_ids)
        for question in questions
    )

    results = []

    for question in questions:
        selected_choices = question.choice_set.filter(
            id__in=selected_ids
        )
        correct_choices = question.choice_set.filter(
            is_correct=True
        )

        is_correct = (
            question.is_get_score(selected_ids) == question.grade
        )

        results.append({
            'question': question,
            'selected_choices': selected_choices,
            'correct_choices': correct_choices,
            'is_correct': is_correct,
        })

    grade = round(total_score / possible * 100) if possible > 0 else 0

    context = {
        'course': course,
        'submission': submission,
        'results': results,
        'grade': grade,
        'total_score': total_score,
        'total_possible': possible,
        'selected_ids': selected_ids,
        'possible': possible,
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context
    )
